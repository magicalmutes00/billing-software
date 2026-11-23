from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_portal
from app.api.v1.helpers import ok
from app.core.config import get_settings
from app.core.context import current_tenant_id
from app.core.errors import bad_request, not_found
from app.core.security import make_token
from app.db.session import get_admin_db, get_db
from app.models import Customer, Invoice, Payment, Quote, Tenant
from app.providers.payments import get_provider
from app.schemas.documents import InvoiceOut, QuoteOut
from app.schemas.payments import AllocationIn, PaymentCreate, PaymentOut
from app.services import payment_service, quote_service

settings = get_settings()
router = APIRouter(prefix="/portal", tags=["portal"])


class PortalTokenIn(BaseModel):
    email: EmailStr
    tenant_slug: str | None = None


@router.post("/token")
async def portal_token(body: PortalTokenIn, session: AsyncSession = Depends(get_admin_db)):
    stmt = select(Customer).where(Customer.email == str(body.email), Customer.deleted_at.is_(None))
    if body.tenant_slug:
        stmt = stmt.join(Tenant, Tenant.id == Customer.tenant_id).where(Tenant.slug == body.tenant_slug)
    customer = await session.scalar(stmt)
    if customer is None:
        raise not_found("No portal account found for this email")
    token = make_token(
        customer.id, customer.tenant_id, kind="portal",
        minutes=settings.portal_token_hours * 60, customer_id=customer.id,
    )
    return ok({"access_token": token, "token_type": "bearer",
               "expires_in": settings.portal_token_hours * 3600, "customer_id": customer.id})


@router.get("/me")
async def portal_me(claims: dict = Depends(require_portal), session: AsyncSession = Depends(get_db)):
    customer = await session.scalar(select(Customer).where(Customer.id == claims["cid"]))
    tenant = await session.scalar(select(Tenant).where(Tenant.id == customer.tenant_id))
    return ok({"id": customer.id, "display_name": customer.display_name, "email": customer.email,
               "tenant_name": tenant.name if tenant else None})


@router.get("/invoices")
async def portal_invoices(claims: dict = Depends(require_portal), session: AsyncSession = Depends(get_db)):
    rows = (await session.scalars(select(Invoice).where(
        Invoice.tenant_id == current_tenant_id(), Invoice.customer_id == claims["cid"]
    ).options(selectinload(Invoice.items)).order_by(Invoice.created_at.desc()))).all()
    return ok([InvoiceOut.model_validate(r) for r in rows])


@router.get("/invoices/{invoice_id}")
async def portal_invoice(invoice_id: str, claims: dict = Depends(require_portal),
                         session: AsyncSession = Depends(get_db)):
    invoice = await session.scalar(select(Invoice).where(
        Invoice.id == invoice_id, Invoice.tenant_id == current_tenant_id(), Invoice.customer_id == claims["cid"]
    ).options(selectinload(Invoice.items)))
    if invoice is None:
        raise not_found("Invoice not found")
    return ok(InvoiceOut.model_validate(invoice))


@router.get("/quotes")
async def portal_quotes(claims: dict = Depends(require_portal), session: AsyncSession = Depends(get_db)):
    rows = (await session.scalars(select(Quote).where(
        Quote.tenant_id == current_tenant_id(), Quote.customer_id == claims["cid"]
    ).options(selectinload(Quote.items)).order_by(Quote.created_at.desc()))).all()
    return ok([QuoteOut.model_validate(r) for r in rows])


@router.post("/quotes/{quote_id}/{action}")
async def portal_quote_action(quote_id: str, action: str, claims: dict = Depends(require_portal),
                              session: AsyncSession = Depends(get_db)):
    quote = await session.scalar(select(Quote).where(
        Quote.id == quote_id, Quote.tenant_id == current_tenant_id(), Quote.customer_id == claims["cid"]
    ))
    if quote is None:
        raise not_found("Quote not found")
    if action == "accept":
        result = await quote_service.accept_quote(session, quote_id)
    elif action == "reject":
        result = await quote_service.reject_quote(session, quote_id)
    else:
        raise bad_request("Unsupported action")
    await session.commit()
    return ok(QuoteOut.model_validate(result))


@router.post("/invoices/{invoice_id}/pay")
async def portal_pay(invoice_id: str, claims: dict = Depends(require_portal),
                     session: AsyncSession = Depends(get_db)):
    invoice = await session.scalar(select(Invoice).where(
        Invoice.id == invoice_id, Invoice.tenant_id == current_tenant_id(), Invoice.customer_id == claims["cid"]
    ))
    if invoice is None:
        raise not_found("Invoice not found")
    if invoice.balance_paise <= 0 or invoice.status == "CANCELLED":
        raise bad_request("Invoice has no payable balance")
    provider = get_provider()
    checkout = await provider.create_payment(
        amount_paise=invoice.balance_paise, currency="INR", order_ref=invoice.id, return_url="/portal/invoices"
    )
    payment = await payment_service.create_payment(session, PaymentCreate(
        customer_id=claims["cid"], amount_paise=invoice.balance_paise, method="GATEWAY",
        provider=provider.name, allocations=[AllocationIn(invoice_id=invoice.id, amount_paise=invoice.balance_paise)],
    ))
    payment.provider_ref = checkout["provider_ref"]
    await session.commit()
    return ok({"payment_id": payment.id, "checkout_url": checkout["checkout_url"],
               "provider_ref": checkout["provider_ref"]})


@router.post("/payments/{payment_id}/simulate")
async def simulate_payment(payment_id: str, claims: dict = Depends(require_portal),
                           session: AsyncSession = Depends(get_db)):
    """Dev-only stub checkout completion; real providers use webhooks."""
    payment = await session.scalar(select(Payment).where(
        Payment.id == payment_id, Payment.customer_id == claims["cid"],
    ))
    if payment is None:
        raise not_found("Payment not found")
    if payment.provider != "stub":
        raise bad_request("Simulation is only available for the stub provider")
    payment = await payment_service.capture_payment(session, payment_id, payment.provider_ref or "stub")
    await session.commit()
    return ok(PaymentOut.model_validate(payment))
