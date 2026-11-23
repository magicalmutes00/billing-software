from __future__ import annotations

from datetime import date, timedelta

from jinja2 import Template
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.context import current_tenant_id
from app.core.errors import bad_request, conflict, not_found
from app.models import Customer, Invoice, InvoiceItem, Tenant
from app.schemas.documents import InvoiceCreate, InvoiceUpdate
from app.services.access import get_customer
from app.services.audit import log_audit
from app.services.numbering import next_number
from app.services.outbox import enqueue
from app.services.tax import calculate_items, is_same_state

settings = get_settings()


async def _tenant(session: AsyncSession) -> Tenant:
    tenant = await session.scalar(select(Tenant).where(Tenant.id == current_tenant_id()))
    if tenant is None:
        raise not_found("Tenant not found")
    return tenant


def _apply_lines(invoice: Invoice, lines: list[dict]) -> None:
    for line in lines:
        invoice.items.append(InvoiceItem(tenant_id=invoice.tenant_id, invoice_id=invoice.id, **line))


def paise_to_inr(paise: int) -> str:
    return f"{paise / 100:,.2f}"


async def list_invoices(
    session: AsyncSession,
    *,
    status: str | None = None,
    customer_id: str | None = None,
    channel: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Invoice], int]:
    where = [Invoice.tenant_id == current_tenant_id()]
    if status:
        where.append(Invoice.status == status)
    if customer_id:
        where.append(Invoice.customer_id == customer_id)
    if channel:
        where.append(Invoice.channel == channel)
    if date_from:
        where.append(Invoice.issue_date >= date_from)
    if date_to:
        where.append(Invoice.issue_date <= date_to)
    if search:
        where.append(func.lower(func.coalesce(Invoice.number, "")).like(f"%{search.lower()}%"))
    stmt = select(Invoice).where(*where)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await session.scalars(
            stmt.options(selectinload(Invoice.items)).order_by(Invoice.created_at.desc())
            .offset((page - 1) * limit).limit(limit)
        )
    ).all()
    return list(rows), total


async def get_invoice(session: AsyncSession, invoice_id: str) -> Invoice:
    row = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == current_tenant_id())
        .options(selectinload(Invoice.items))
    )
    if row is None:
        raise not_found("Invoice not found")
    return row


async def create_invoice(session: AsyncSession, data: InvoiceCreate) -> Invoice:
    tenant = await _tenant(session)
    customer = await get_customer(session, data.customer_id)
    calc = calculate_items(
        data.items,
        tax_mode=data.tax_mode,
        same_state=is_same_state(tenant.state_code, customer.state_code),
    )
    due_date = data.due_date or data.issue_date + timedelta(days=customer.payment_terms_days)
    invoice = Invoice(
        tenant_id=tenant.id,
        customer_id=data.customer_id,
        quote_id=data.quote_id,
        issue_date=data.issue_date,
        due_date=due_date,
        subtotal_paise=calc["subtotal_paise"],
        discount_paise=calc["discount_paise"],
        tax_paise=calc["tax_paise"],
        round_off_paise=calc["round_off_paise"],
        total_paise=calc["payable_paise"],
        balance_paise=calc["payable_paise"],
        currency=data.currency,
        notes=data.notes,
        terms=data.terms,
        tax_mode=data.tax_mode,
        place_of_supply=customer.state_code,
        status="DRAFT",
        items=[],
    )
    session.add(invoice)
    await session.flush()
    _apply_lines(invoice, calc["lines"])
    await log_audit(session, action="invoice.create", entity_type="invoice", entity_id=invoice.id, after={"total_paise": invoice.total_paise})
    await session.flush()
    return invoice


async def update_invoice(session: AsyncSession, invoice_id: str, data: InvoiceUpdate) -> Invoice:
    invoice = await get_invoice(session, invoice_id)
    if invoice.status not in {"DRAFT", "SENT"}:
        raise conflict("Only draft or sent invoices can be edited")
    if data.version is not None and data.version != invoice.version:
        raise conflict("Invoice was modified by someone else", {"current_version": invoice.version})
    payload = data.model_dump(exclude_unset=True, exclude={"items", "version"})
    if "customer_id" in payload:
        await get_customer(session, payload["customer_id"])
    for field, value in payload.items():
        setattr(invoice, field, value)
    if data.items is not None:
        tenant = await _tenant(session)
        customer = await get_customer(session, invoice.customer_id)
        calc = calculate_items(
            data.items,
            tax_mode=invoice.tax_mode,
            same_state=is_same_state(tenant.state_code, customer.state_code),
        )
        invoice.subtotal_paise = calc["subtotal_paise"]
        invoice.discount_paise = calc["discount_paise"]
        invoice.tax_paise = calc["tax_paise"]
        invoice.round_off_paise = calc["round_off_paise"]
        invoice.total_paise = calc["payable_paise"]
        invoice.balance_paise = max(0, calc["payable_paise"] - invoice.paid_paise - invoice.credited_paise)
        invoice.items.clear()  # delete-orphan cascade removes the old rows on flush
        await session.flush()
        _apply_lines(invoice, calc["lines"])
    invoice.version += 1
    await log_audit(session, action="invoice.update", entity_type="invoice", entity_id=invoice.id, after=payload)
    await session.flush()
    return invoice


async def send_invoice(session: AsyncSession, invoice_id: str, *, number_kind: str = "INVOICE") -> Invoice:
    invoice = await get_invoice(session, invoice_id)
    if invoice.status not in {"DRAFT", "SENT"}:
        raise conflict("Invoice cannot be sent from its current status")
    if invoice.number is None:
        invoice.number = await next_number(session, invoice.tenant_id, number_kind, when=invoice.issue_date)
    from app.core.security import utcnow

    invoice.sent_at = utcnow()
    if invoice.status == "DRAFT":
        invoice.status = "PARTIALLY_PAID" if invoice.paid_paise > 0 else "SENT"
    await enqueue(session, "invoice.sent", {"invoice_id": invoice.id, "tenant_id": invoice.tenant_id})
    await log_audit(session, action="invoice.send", entity_type="invoice", entity_id=invoice.id, after={"number": invoice.number})
    await session.flush()
    return invoice


async def cancel_invoice(session: AsyncSession, invoice_id: str) -> Invoice:
    invoice = await get_invoice(session, invoice_id)
    if invoice.paid_paise > 0:
        raise conflict("Paid invoices cannot be cancelled; issue a credit note instead")
    if invoice.status == "CANCELLED":
        raise conflict("Invoice is already cancelled")
    invoice.status = "CANCELLED"
    await log_audit(session, action="invoice.cancel", entity_type="invoice", entity_id=invoice.id)
    await session.flush()
    return invoice


async def mark_overdue(session: AsyncSession, tenant_id: str) -> int:
    rows = (await session.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(["SENT", "PARTIALLY_PAID"]),
            Invoice.due_date < date.today(),
        )
    )).all()
    for invoice in rows:
        invoice.status = "OVERDUE"
        await log_audit(session, action="invoice.overdue", entity_type="invoice", entity_id=invoice.id)
    await session.flush()
    return len(rows)


INVOICE_TEMPLATE = Template(
    """<!doctype html><html><head><meta charset="utf-8"><style>
@page{size:A4;margin:16mm}body{font-family:Arial,sans-serif;color:#111;font-size:12px}
h1{font-size:22px;margin:0}table{width:100%;border-collapse:collapse;margin-top:18px}
th,td{border-bottom:1px solid #ddd;padding:7px;text-align:left}th{background:#f4f4f5}
.right{text-align:right}.total{font-size:15px;font-weight:bold}
</style></head><body>
<div style="display:flex;justify-content:space-between">
<div><h1>{{ tenant.name }}</h1><div>{{ tenant.legal_name or '' }}</div>
<div>GSTIN: {{ tenant.gstin or '—' }}</div><div>{{ tenant.address_line1 or '' }} {{ tenant.city or '' }} {{ tenant.pincode or '' }}</div></div>
<div><h2>{{ 'TAX INVOICE' if invoice.number else 'DRAFT' }}</h2>
<div><b>{{ invoice.number or 'Draft' }}</b></div><div>Date: {{ invoice.issue_date }}</div>
<div>Due: {{ invoice.due_date }}</div></div></div>
<hr>
<div><b>Bill to</b><div>{{ customer.legal_name }}</div><div>GSTIN: {{ customer.gstin or '—' }}</div>
<div>{{ customer.email or '' }}</div></div>
<table><thead><tr><th>#</th><th>Description</th><th>HSN/SAC</th><th class="right">Qty</th>
<th class="right">Rate</th><th class="right">Tax</th><th class="right">Amount</th></tr></thead><tbody>
{% for item in invoice.items %}<tr><td>{{ loop.index }}</td><td>{{ item.description }}</td>
<td>{{ item.hsn_sac or '—' }}</td><td class="right">{{ item.qty }}</td>
<td class="right">{{ paise_to_inr(item.unit_price_paise) }}</td>
<td class="right">{{ paise_to_inr(item.tax_paise) }}</td>
<td class="right">{{ paise_to_inr(item.total_paise) }}</td></tr>{% endfor %}
</tbody></table>
<div style="margin-top:16px" class="right">
<div>Subtotal: {{ paise_to_inr(invoice.subtotal_paise) }}</div>
<div>Discount: {{ paise_to_inr(invoice.discount_paise) }}</div>
<div>GST: {{ paise_to_inr(invoice.tax_paise) }}</div>
<div>Round off: {{ paise_to_inr(invoice.round_off_paise) }}</div>
<div class="total">Total: {{ paise_to_inr(invoice.total_paise) }}</div>
<div>Paid: {{ paise_to_inr(invoice.paid_paise) }}</div>
<div class="total">Balance: {{ paise_to_inr(invoice.balance_paise) }}</div></div>
<div style="margin-top:30px">{{ invoice.notes or '' }}</div></body></html>"""
)


async def invoice_html(session: AsyncSession, invoice_id: str) -> str:
    invoice = await get_invoice(session, invoice_id)
    tenant = await _tenant(session)
    customer = await get_customer(session, invoice.customer_id)
    return INVOICE_TEMPLATE.render(invoice=invoice, tenant=tenant, customer=customer, paise_to_inr=paise_to_inr)
