from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import current_tenant_id
from app.core.errors import bad_request, conflict, not_found
from app.models import Customer, Invoice, Payment, PaymentAllocation
from app.schemas.payments import AllocateIn, AllocationIn, PaymentCreate
from app.services.access import get_customer, get_invoice
from app.services.audit import log_audit
from app.services.numbering import next_number
from app.services.outbox import enqueue


async def list_payments(
    session: AsyncSession, *, customer_id: str | None = None, status: str | None = None,
    page: int = 1, limit: int = 20
) -> tuple[list[Payment], int]:
    where = [Payment.tenant_id == current_tenant_id()]
    if customer_id:
        where.append(Payment.customer_id == customer_id)
    if status:
        where.append(Payment.status == status)
    stmt = select(Payment).where(*where)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await session.scalars(stmt.options(selectinload(Payment.allocations)).order_by(Payment.created_at.desc())
                              .offset((page - 1) * limit).limit(limit))
    ).all()
    return list(rows), total


async def get_payment(session: AsyncSession, payment_id: str) -> Payment:
    row = await session.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.tenant_id == current_tenant_id())
        .options(selectinload(Payment.allocations))
    )
    if row is None:
        raise not_found("Payment not found")
    return row


def _invoice_status(invoice: Invoice) -> str:
    if invoice.balance_paise <= 0:
        return "PAID"
    if invoice.status == "OVERDUE":
        return "OVERDUE"
    return "PARTIALLY_PAID"


async def apply_allocations(session: AsyncSession, payment: Payment, lines: list[AllocationIn]) -> None:
    allocated = sum(a.amount_paise for a in payment.allocations)
    remaining = payment.amount_paise - allocated
    requested = sum(line.amount_paise for line in lines)
    if requested > remaining:
        raise bad_request(f"Allocations exceed unallocated amount ({remaining} paise)")
    if not lines:
        return
    for line in lines:
        invoice = await get_invoice(session, line.invoice_id)
        if invoice.customer_id != payment.customer_id:
            raise bad_request("Payment and invoice customers do not match")
        if invoice.status in {"CANCELLED", "PAID"}:
            raise conflict(f"Invoice {invoice.number or invoice.id} cannot receive payments")
        if line.amount_paise > invoice.balance_paise:
            raise bad_request(f"Allocation exceeds invoice balance ({invoice.balance_paise} paise)")
        payment.allocations.append(
            PaymentAllocation(
                tenant_id=payment.tenant_id,
                invoice_id=invoice.id,
                amount_paise=line.amount_paise,
            )
        )
        invoice.paid_paise += line.amount_paise
        invoice.balance_paise = max(0, invoice.balance_paise - line.amount_paise)
        invoice.status = _invoice_status(invoice)
    await session.flush()


async def create_payment(session: AsyncSession, data: PaymentCreate) -> Payment:
    tenant_id = current_tenant_id()
    customer = await get_customer(session, data.customer_id)
    captured = data.method != "GATEWAY" or bool(data.provider_ref)
    payment = Payment(
        tenant_id=tenant_id,
        customer_id=customer.id,
        amount_paise=data.amount_paise,
        method=data.method,
        provider=data.provider,
        provider_ref=data.provider_ref,
        reference_no=data.reference_no,
        notes=data.notes,
        paid_at=data.paid_at or (datetime.now() if captured else None),
        status="CAPTURED" if captured else "PENDING",
        created_by=session.info.get("actor_id"),
        allocations=[],
    )
    session.add(payment)
    await session.flush()
    if captured:
        payment.number = await next_number(session, tenant_id, "PAYMENT", when=(payment.paid_at or datetime.now()).date())
    if data.allocations:
        await apply_allocations(session, payment, data.allocations)
    payment.allocated_paise = sum(a.amount_paise for a in payment.allocations)
    await enqueue(session, "payment.recorded", {"payment_id": payment.id, "tenant_id": tenant_id})
    await log_audit(session, action="payment.create", entity_type="payment", entity_id=payment.id,
                    after={"amount_paise": payment.amount_paise, "customer_id": customer.id})
    await session.flush()
    return payment


async def allocate_payment(session: AsyncSession, payment_id: str, data: AllocateIn) -> Payment:
    payment = await get_payment(session, payment_id)
    if payment.status != "CAPTURED":
        raise conflict("Only captured payments can be allocated")
    await apply_allocations(session, payment, data.allocations)
    payment.allocated_paise = sum(a.amount_paise for a in payment.allocations)
    await log_audit(session, action="payment.allocate", entity_type="payment", entity_id=payment.id,
                    after={"allocated_paise": payment.allocated_paise})
    await session.flush()
    return payment


async def capture_payment(session: AsyncSession, payment_id: str, provider_ref: str) -> Payment:
    payment = await get_payment(session, payment_id)
    if payment.status == "CAPTURED":
        return payment
    payment.status = "CAPTURED"
    payment.provider_ref = provider_ref
    payment.paid_at = datetime.now()
    payment.number = await next_number(session, payment.tenant_id, "PAYMENT", when=payment.paid_at.date())
    await session.flush()
    return payment


async def refund_payment(session: AsyncSession, payment_id: str, amount_paise: int | None = None) -> Payment:
    payment = await get_payment(session, payment_id)
    if payment.status != "CAPTURED":
        raise conflict("Only captured payments can be refunded")
    if amount_paise is not None and amount_paise != payment.amount_paise:
        raise bad_request("Partial refunds must be issued as credit notes")
    for allocation in payment.allocations:
        invoice = await get_invoice(session, allocation.invoice_id)
        invoice.paid_paise = max(0, invoice.paid_paise - allocation.amount_paise)
        invoice.balance_paise = min(invoice.total_paise, invoice.balance_paise + allocation.amount_paise)
        invoice.status = "OVERDUE" if invoice.due_date < datetime.now().date() else "PARTIALLY_PAID"
        if invoice.balance_paise >= invoice.total_paise:
            invoice.status = "SENT" if invoice.due_date >= datetime.now().date() else "OVERDUE"
        await session.delete(allocation)
    payment.status = "REFUNDED"
    payment.allocated_paise = 0
    await log_audit(session, action="payment.refund", entity_type="payment", entity_id=payment.id,
                    after={"amount_paise": payment.amount_paise})
    await session.flush()
    return payment
