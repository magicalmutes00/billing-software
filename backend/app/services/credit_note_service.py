from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import current_tenant_id
from app.core.errors import bad_request, conflict, not_found
from app.models import CreditNote, CreditNoteAllocation, Invoice, Tenant
from app.schemas.payments import CreditNoteCreate
from app.services.access import get_customer, get_invoice
from app.services.audit import log_audit
from app.services.numbering import next_number
from app.services.tax import calculate_items, is_same_state


async def list_credit_notes(session: AsyncSession, page: int = 1, limit: int = 20) -> tuple[list[CreditNote], int]:
    stmt = select(CreditNote).where(CreditNote.tenant_id == current_tenant_id())
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.order_by(CreditNote.created_at.desc()).offset((page - 1) * limit).limit(limit))).all()
    return list(rows), total


async def get_credit_note(session: AsyncSession, note_id: str) -> CreditNote:
    row = await session.scalar(
        select(CreditNote).where(CreditNote.id == note_id, CreditNote.tenant_id == current_tenant_id())
        .options(selectinload(CreditNote.allocations))
    )
    if row is None:
        raise not_found("Credit note not found")
    return row


async def create_credit_note(session: AsyncSession, data: CreditNoteCreate) -> CreditNote:
    tenant_id = current_tenant_id()
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    customer = await get_customer(session, data.customer_id)
    calc = calculate_items(
        data.items,
        tax_mode=data.tax_mode,
        same_state=is_same_state(tenant.state_code if tenant else "KA", customer.state_code),
    )
    note = CreditNote(
        tenant_id=tenant_id,
        customer_id=customer.id,
        invoice_id=data.invoice_id,
        reason=data.reason,
        subtotal_paise=calc["subtotal_paise"],
        tax_paise=calc["tax_paise"],
        total_paise=calc["payable_paise"],
        tax_mode=data.tax_mode,
        cgst_paise=calc["cgst_paise"],
        sgst_paise=calc["sgst_paise"],
        igst_paise=calc["igst_paise"],
        refund_mode=data.refund_mode,
        status="DRAFT",
    )
    session.add(note)
    await log_audit(session, action="credit_note.create", entity_type="credit_note", entity_id=note.id,
                    after={"total_paise": note.total_paise})
    await session.flush()
    return note


async def issue_credit_note(session: AsyncSession, note_id: str) -> CreditNote:
    note = await get_credit_note(session, note_id)
    if note.status != "DRAFT":
        raise conflict("Only draft credit notes can be issued")
    note.number = await next_number(session, note.tenant_id, "CREDIT_NOTE")
    note.status = "ISSUED"
    await log_audit(session, action="credit_note.issue", entity_type="credit_note", entity_id=note.id,
                    after={"number": note.number})
    await session.flush()
    return note


async def apply_credit_note(session: AsyncSession, note_id: str, invoice_id: str | None = None,
                            amount_paise: int | None = None) -> CreditNote:
    note = await get_credit_note(session, note_id)
    if note.status not in {"ISSUED", "APPLIED"}:
        raise conflict("Credit note must be issued before applying")
    target_id = invoice_id or note.invoice_id
    if not target_id:
        raise bad_request("invoice_id is required")
    invoice = await get_invoice(session, target_id)
    if invoice.customer_id != note.customer_id:
        raise bad_request("Credit note and invoice customers do not match")
    remaining = note.total_paise - note.applied_paise
    amount = min(amount_paise or remaining, remaining, invoice.balance_paise)
    if amount <= 0:
        raise bad_request("No applicable amount remains")
    existing = next((a for a in note.allocations if a.invoice_id == invoice.id), None)
    if existing:
        existing.amount_paise += amount
    else:
        note.allocations.append(CreditNoteAllocation(tenant_id=note.tenant_id,
                                                     invoice_id=invoice.id, amount_paise=amount))
    invoice.credited_paise += amount
    invoice.balance_paise = max(0, invoice.balance_paise - amount)
    if invoice.balance_paise == 0:
        invoice.status = "PAID"
    note.applied_paise += amount
    if note.applied_paise >= note.total_paise:
        note.status = "APPLIED"
    await log_audit(session, action="credit_note.apply", entity_type="credit_note", entity_id=note.id,
                    after={"invoice_id": invoice.id, "amount_paise": amount})
    await session.flush()
    return note


async def void_credit_note(session: AsyncSession, note_id: str) -> CreditNote:
    note = await get_credit_note(session, note_id)
    if note.applied_paise > 0:
        raise conflict("Applied credit notes cannot be voided")
    note.status = "VOID"
    await log_audit(session, action="credit_note.void", entity_type="credit_note", entity_id=note.id)
    await session.flush()
    return note
