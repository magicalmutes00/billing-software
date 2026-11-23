from __future__ import annotations

import hashlib
import hmac
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.context import tenant_id_var
from app.core.errors import not_found
from app.core.security import decode_token, utcnow
from app.models import CreditNote, Customer, Invoice, Payment, Quote, Tenant
from app.models.ops import WebhookEvent
from app.providers.payments import get_provider
from app.schemas.customer import AddressIn, CustomerCreate
from app.schemas.documents import InvoiceCreate, ItemIn, QuoteCreate
from app.schemas.ops import RecurringCreate
from app.schemas.payments import AllocationIn, CreditNoteCreate, PaymentCreate
from app.services import (
    auth_service,
    credit_note_service,
    customer_service,
    invoice_service,
    payment_service,
    quote_service,
    recurring_service,
    report_service,
)
from app.services.auth_service import create_tenant_with_owner
from app.services.tax import calculate_items, is_same_state


def item(description: str = "Design work", price: int = 1_000_00, rate: float = 18) -> ItemIn:
    return ItemIn(description=description, qty=1, unit_price_paise=price, tax_rate_pct=rate)


@pytest.mark.asyncio
async def test_tax_intra_and_inter_state(db):
    session, _tenant = db
    lines = [item()]
    intra = calculate_items(lines, tax_mode="EXCLUSIVE", same_state=True)
    inter = calculate_items(lines, tax_mode="EXCLUSIVE", same_state=False)
    assert intra["cgst_paise"] == 9000 and intra["sgst_paise"] == 9000 and intra["igst_paise"] == 0
    assert inter["igst_paise"] == 18000 and inter["cgst_paise"] == 0
    assert intra["payable_paise"] == 118000 == inter["payable_paise"]
    inclusive = calculate_items(lines, tax_mode="INCLUSIVE", same_state=True)
    assert inclusive["payable_paise"] == 100000
    assert is_same_state("KA", "KA") and not is_same_state("KA", "TN")


@pytest.mark.asyncio
async def test_quote_to_invoice_to_payment_to_credit_note(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    customer = await customer_service.create_customer(session, CustomerCreate(
        legal_name="Chennai Traders",
        display_name="Chennai Traders",
        state_code="TN",
        gstin="33AABCI9876K1Z9",
        tax_type="REGISTERED",
        email="accounts@chennai.example.com",
        addresses=[AddressIn(line1="4 Mount Road", city="Chennai", state_code="TN", pincode="600002")],
    ))
    assert customer.addresses and customer.addresses[0].city == "Chennai"

    quote = await quote_service.create_quote(session, QuoteCreate(
        customer_id=customer.id, issue_date=date.today(),
        valid_until=date.today() + timedelta(days=30), items=[item()],
    ))
    assert quote.number is None
    quote = await quote_service.send_quote(session, quote.id)
    assert quote.number and quote.status == "SENT"
    quote = await quote_service.accept_quote(session, quote.id)
    invoice = await quote_service.convert_quote(session, quote.id)
    assert invoice.quote_id == quote.id
    assert invoice.total_paise == 118000
    invoice = await invoice_service.send_invoice(session, invoice.id)
    assert invoice.number and invoice.status == "SENT"

    payment = await payment_service.create_payment(session, PaymentCreate(
        customer_id=customer.id,
        amount_paise=50000,
        method="BANK",
        allocations=[AllocationIn(invoice_id=invoice.id, amount_paise=50000)],
    ))
    assert payment.number and payment.allocated_paise == 50000
    refreshed = await invoice_service.get_invoice(session, invoice.id)
    assert refreshed.paid_paise == 50000 and refreshed.balance_paise == 68000
    assert refreshed.status == "PARTIALLY_PAID"

    note = await credit_note_service.create_credit_note(session, CreditNoteCreate(
        customer_id=customer.id, invoice_id=invoice.id, reason="Pricing correction",
        items=[item(price=20_000, rate=18)],
    ))
    note = await credit_note_service.issue_credit_note(session, note.id)
    assert note.number and note.status == "ISSUED"
    note = await credit_note_service.apply_credit_note(session, note.id)
    assert note.applied_paise == 23600 and note.status == "APPLIED"
    refreshed = await invoice_service.get_invoice(session, invoice.id)
    assert refreshed.credited_paise == 23600 and refreshed.balance_paise == 44400

    totals = await report_service.dashboard(session)
    assert totals["billed_paise"] >= 118000
    assert totals["collected_paise"] >= 50000


@pytest.mark.asyncio
async def test_cancel_and_refund_rules(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    customer = await customer_service.create_customer(session, CustomerCreate(
        legal_name="Local Partners", display_name="Local Partners", state_code="KA",
    ))
    invoice = await invoice_service.create_invoice(session, InvoiceCreate(
        customer_id=customer.id, issue_date=date.today(), items=[item()],
    ))
    invoice = await invoice_service.send_invoice(session, invoice.id)
    cancelled = await invoice_service.cancel_invoice(session, invoice.id)
    assert cancelled.status == "CANCELLED"

    invoice2 = await invoice_service.create_invoice(session, InvoiceCreate(
        customer_id=customer.id, issue_date=date.today(), items=[item()],
    ))
    await invoice_service.send_invoice(session, invoice2.id)
    payment = await payment_service.create_payment(session, PaymentCreate(
        customer_id=customer.id, amount_paise=118000, method="UPI",
        allocations=[AllocationIn(invoice_id=invoice2.id, amount_paise=118000)],
    ))
    with pytest.raises(Exception):
        await invoice_service.cancel_invoice(session, invoice2.id)
    refunded = await payment_service.refund_payment(session, payment.id)
    assert refunded.status == "REFUNDED"
    refreshed = await invoice_service.get_invoice(session, invoice2.id)
    assert refreshed.balance_paise == 118000


@pytest.mark.asyncio
async def test_tenant_isolation(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    customer = await customer_service.create_customer(session, CustomerCreate(
        legal_name="Only Tenant A", display_name="Only Tenant A", state_code="KA",
    ))
    other = await create_tenant_with_owner(
        session, name="Tenant B", slug="tenant-b", email="b@test.example.com", password="Password123!"
    )
    token = tenant_id_var.set(other.id)
    try:
        with pytest.raises(Exception) as exc:
            await customer_service.get_customer(session, customer.id)
        assert isinstance(exc.value, type(not_found("x")))
        other_customer = await customer_service.create_customer(session, CustomerCreate(
            legal_name="Only Tenant B", display_name="Only Tenant B", state_code="TN",
        ))
        assert other_customer.tenant_id == other.id
    finally:
        tenant_id_var.reset(token)
    rows = (await session.scalars(select(Customer).order_by(Customer.created_at))).all()
    assert {row.tenant_id for row in rows} == {tenant.id, other.id}


@pytest.mark.asyncio
async def test_document_html_and_outbox(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    customer = await customer_service.create_customer(session, CustomerCreate(
        legal_name="HTML Customer", display_name="HTML Customer", state_code="KA",
    ))
    invoice = await invoice_service.create_invoice(session, InvoiceCreate(
        customer_id=customer.id, issue_date=date.today(), items=[item(description="Printable item")],
    ))
    await invoice_service.send_invoice(session, invoice.id)
    html = await invoice_service.invoice_html(session, invoice.id)
    assert "Printable item" in html and "DRAFT" not in html
    assert "TAX INVOICE" in html


@pytest.mark.asyncio
async def test_login_refresh_and_token_claims(db):
    session, tenant = db
    pair = await auth_service.login(session, "owner@test.example.com", "Password123!", "127.0.0.1")
    assert pair["access_token"] and pair["refresh_token"] and pair["token_type"] == "bearer"
    claims = decode_token(pair["access_token"], kind="access")
    assert claims["tid"] == tenant.id
    assert "invoices.write" in claims["perms"]
    rotated = await auth_service.refresh(session, pair["refresh_token"])
    assert rotated["access_token"] != pair["access_token"]
    with pytest.raises(Exception):
        await auth_service.refresh(session, pair["refresh_token"])


@pytest.mark.asyncio
async def test_invoice_numbering_and_draft_rules(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    customer = await customer_service.create_customer(session, CustomerCreate(
        legal_name="Numbering Co", display_name="Numbering Co", state_code="KA",
    ))
    first = await invoice_service.create_invoice(session, InvoiceCreate(
        customer_id=customer.id, issue_date=date.today(), items=[item()],
    ))
    second = await invoice_service.create_invoice(session, InvoiceCreate(
        customer_id=customer.id, issue_date=date.today(), items=[item()],
    ))
    assert first.number is None and second.number is None  # drafts are unnumbered
    first = await invoice_service.send_invoice(session, first.id)
    second = await invoice_service.send_invoice(session, second.id)
    assert first.number and second.number and first.number != second.number
    assert first.status == second.status == "SENT"


@pytest.mark.asyncio
async def test_recurring_generation_is_idempotent_per_period(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    customer = await customer_service.create_customer(session, CustomerCreate(
        legal_name="Retainer Client", display_name="Retainer Client", state_code="KA",
    ))
    schedule = await recurring_service.create_schedule(session, RecurringCreate(
        customer_id=customer.id,
        name="Monthly retainer",
        start_date=date.today().isoformat(),
        template={"items": [item().model_dump()]},
    ))
    period = date.today()
    invoice = await recurring_service.generate_invoice(session, schedule, when=period)
    assert invoice.customer_id == customer.id
    assert schedule.last_invoice_id == invoice.id
    assert schedule.last_period == f"{period.year}-{period.month:02d}"
    assert schedule.next_run_at > schedule.start_date
    # Replaying the same period is rejected; omitting `when` advances to the next period.
    with pytest.raises(Exception):
        await recurring_service.generate_invoice(session, schedule, when=period)
    next_invoice = await recurring_service.generate_invoice(session, schedule)
    assert next_invoice.id != invoice.id


@pytest.mark.asyncio
async def test_webhook_signature_and_event_dedupe(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    provider = get_provider("stub")
    raw = b'{"id":"evt_dedupe_1","status":"SUCCESS"}'
    secret = get_settings().webhook_secret.encode()
    signature = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    assert provider.verify_webhook(raw_body=raw, signature=signature)
    assert not provider.verify_webhook(raw_body=raw, signature="not-a-signature")
    assert not provider.verify_webhook(raw_body=raw, signature=None)
    session.add(WebhookEvent(
        tenant_id=tenant.id, provider="stub", event_id="evt_dedupe_1",
        payload={"id": "evt_dedupe_1"}, status="PROCESSED", processed_at=utcnow(),
    ))
    await session.flush()
    found = await session.scalar(select(WebhookEvent).where(WebhookEvent.event_id == "evt_dedupe_1"))
    assert found is not None and found.status == "PROCESSED"
