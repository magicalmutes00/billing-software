from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import current_tenant_id
from app.core.errors import bad_request, conflict, not_found
from app.models import Invoice, Quote, QuoteItem
from app.schemas.documents import InvoiceCreate, ItemIn, QuoteCreate, QuoteUpdate
from app.services.access import get_customer
from app.services.audit import log_audit
from app.services.numbering import next_number
from app.services.tax import calculate_items, is_same_state
from app.services.outbox import enqueue


def _apply_quote_items(quote: Quote, lines: list[dict]) -> None:
    for line in lines:
        quote.items.append(QuoteItem(tenant_id=quote.tenant_id, quote_id=quote.id, **line))


async def list_quotes(
    session: AsyncSession, *, status: str | None = None, customer_id: str | None = None,
    page: int = 1, limit: int = 20
) -> tuple[list[Quote], int]:
    where = [Quote.tenant_id == current_tenant_id()]
    if status:
        where.append(Quote.status == status)
    if customer_id:
        where.append(Quote.customer_id == customer_id)
    stmt = select(Quote).where(*where)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.order_by(Quote.created_at.desc()).offset((page - 1) * limit).limit(limit))).all()
    return list(rows), total


async def get_quote(session: AsyncSession, quote_id: str) -> Quote:
    row = await session.scalar(
        select(Quote).where(Quote.id == quote_id, Quote.tenant_id == current_tenant_id()).options(selectinload(Quote.items))
    )
    if row is None:
        raise not_found("Quote not found")
    return row


async def create_quote(session: AsyncSession, data: QuoteCreate) -> Quote:
    tenant_id = current_tenant_id()
    customer = await get_customer(session, data.customer_id)
    calc = calculate_items(
        data.items,
        same_state=is_same_state((await _tenant_state(session)) or "KA", customer.state_code),
    )
    quote = Quote(
        tenant_id=tenant_id,
        customer_id=data.customer_id,
        issue_date=data.issue_date,
        valid_until=data.valid_until,
        subtotal_paise=calc["subtotal_paise"],
        discount_paise=calc["discount_paise"],
        tax_paise=calc["tax_paise"],
        total_paise=calc["payable_paise"],
        currency=data.currency,
        notes=data.notes,
        terms=data.terms,
        items=[],
    )
    session.add(quote)
    await session.flush()
    _apply_quote_items(quote, calc["lines"])
    await log_audit(session, action="quote.create", entity_type="quote", entity_id=quote.id, after={"total_paise": quote.total_paise})
    await session.flush()
    return quote


async def _tenant_state(session: AsyncSession) -> str | None:
    from app.models import Tenant

    tenant = await session.scalar(select(Tenant).where(Tenant.id == current_tenant_id()))
    return tenant.state_code if tenant else None


async def update_quote(session: AsyncSession, quote_id: str, data: QuoteUpdate) -> Quote:
    quote = await get_quote(session, quote_id)
    if quote.status not in {"DRAFT", "SENT"}:
        raise conflict("Only draft or sent quotes can be edited")
    if data.version is not None and data.version != quote.version:
        raise conflict("Quote was modified by someone else", {"current_version": quote.version})
    payload = data.model_dump(exclude_unset=True, exclude={"items", "version"})
    for field, value in payload.items():
        setattr(quote, field, value)
    if data.items is not None:
        customer = await get_customer(session, quote.customer_id)
        calc = calculate_items(
            data.items,
            same_state=is_same_state((await _tenant_state(session)) or "KA", customer.state_code),
        )
        quote.subtotal_paise = calc["subtotal_paise"]
        quote.discount_paise = calc["discount_paise"]
        quote.tax_paise = calc["tax_paise"]
        quote.total_paise = calc["payable_paise"]
        quote.items.clear()  # delete-orphan cascade removes the old rows on flush
        await _apply_quote_items(quote, calc["lines"])
    quote.version += 1
    await log_audit(session, action="quote.update", entity_type="quote", entity_id=quote.id, after=payload)
    await session.flush()
    return quote


async def send_quote(session: AsyncSession, quote_id: str) -> Quote:
    quote = await get_quote(session, quote_id)
    if quote.status != "DRAFT":
        raise conflict("Only draft quotes can be sent")
    if quote.number is None:
        quote.number = await next_number(session, quote.tenant_id, "QUOTE", when=quote.issue_date)
    from app.core.security import utcnow

    quote.sent_at = utcnow()
    quote.status = "SENT"
    await enqueue(session, "quote.sent", {"quote_id": quote.id, "tenant_id": quote.tenant_id})
    await log_audit(session, action="quote.send", entity_type="quote", entity_id=quote.id)
    await session.flush()
    return quote


async def accept_quote(session: AsyncSession, quote_id: str) -> Quote:
    quote = await get_quote(session, quote_id)
    if quote.status != "SENT":
        raise conflict("Only sent quotes can be accepted")
    from app.core.security import utcnow

    quote.status = "ACCEPTED"
    quote.accepted_at = utcnow()
    await log_audit(session, action="quote.accept", entity_type="quote", entity_id=quote.id)
    await session.flush()
    return quote


async def reject_quote(session: AsyncSession, quote_id: str) -> Quote:
    quote = await get_quote(session, quote_id)
    if quote.status != "SENT":
        raise conflict("Only sent quotes can be rejected")
    quote.status = "REJECTED"
    await log_audit(session, action="quote.reject", entity_type="quote", entity_id=quote.id)
    await session.flush()
    return quote


async def expire_quotes(session: AsyncSession) -> int:
    now = date.today()
    rows = (await session.scalars(
        select(Quote).where(Quote.tenant_id == current_tenant_id(), Quote.status == "SENT", Quote.valid_until < now)
    )).all()
    for quote in rows:
        quote.status = "EXPIRED"
    await session.flush()
    return len(rows)


async def convert_quote(session: AsyncSession, quote_id: str) -> Invoice:
    from app.services.invoice_service import create_invoice

    quote = await get_quote(session, quote_id)
    if quote.status not in {"SENT", "ACCEPTED"}:
        raise bad_request("Quote must be sent or accepted before conversion")
    if quote.converted_invoice_id:
        raise conflict("Quote has already been converted")
    items = [ItemIn.model_validate(item, from_attributes=True) for item in quote.items]
    invoice = await create_invoice(
        session,
        InvoiceCreate(
            customer_id=quote.customer_id,
            issue_date=date.today(),
            items=items,
            notes=quote.notes,
            terms=quote.terms,
            quote_id=quote.id,
        ),
    )
    quote.status = "CONVERTED"
    quote.converted_invoice_id = invoice.id
    await log_audit(session, action="quote.convert", entity_type="quote", entity_id=quote.id, after={"invoice_id": invoice.id})
    await session.flush()
    return invoice
