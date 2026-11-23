from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import tenant_id_var
from app.models import Invoice, OutboxEvent, RecurringSchedule, Reminder
from app.models.tenant import Tenant
from app.services.invoice_service import mark_overdue
from app.services.outbox import enqueue
from app.services.quote_service import expire_quotes
from app.services.recurring_service import generate_invoice


async def process_outbox(session: AsyncSession, tenant_id: str) -> int:
    rows = (await session.scalars(
        select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id, OutboxEvent.status == "PENDING")
    )).all()
    for event in rows:
        # Delivery adapters (email/SMS) plug in here. At-least-once with idempotent handlers.
        event.status = "DONE"
        event.attempts += 1
    await session.flush()
    return len(rows)


async def schedule_reminders(session: AsyncSession, tenant_id: str) -> int:
    today = date.today()
    offsets = {"PRE_DUE_7": -7, "PRE_DUE_3": -3, "DUE": 0, "OVERDUE_7": 7}
    invoices = (await session.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.balance_paise > 0,
            Invoice.status.notin_(["CANCELLED", "PAID"]),
        )
    )).all()
    created = 0
    for invoice in invoices:
        for kind, offset in offsets.items():
            due_at = invoice.due_date + timedelta(days=offset)
            if due_at != today:
                continue
            existing = await session.scalar(
                select(Reminder).where(
                    Reminder.tenant_id == tenant_id,
                    Reminder.invoice_id == invoice.id,
                    Reminder.kind == kind,
                    Reminder.due_at == due_at.isoformat(),
                )
            )
            if existing:
                continue
            session.add(Reminder(tenant_id=tenant_id, invoice_id=invoice.id, kind=kind,
                                 due_at=due_at.isoformat()))
            session.add(OutboxEvent(tenant_id=tenant_id, type=f"reminder.{kind.lower()}",
                                    payload={"invoice_id": invoice.id, "due_at": due_at.isoformat()},
                                    status="PENDING"))
            created += 1
    await session.flush()
    return created


async def process_recurring(session: AsyncSession, tenant_id: str) -> int:
    today = date.today().isoformat()
    schedules = (await session.scalars(
        select(RecurringSchedule).where(
            RecurringSchedule.tenant_id == tenant_id,
            RecurringSchedule.status == "ACTIVE",
            RecurringSchedule.next_run_at <= today,
        )
    )).all()
    created = 0
    for schedule in schedules:
        if schedule.end_date and schedule.next_run_at > schedule.end_date:
            schedule.status = "CANCELLED"
            continue
        try:
            await generate_invoice(session, schedule)
            created += 1
        except Exception:  # keep the batch running; failures are visible via audit/outbox
            session.add(OutboxEvent(tenant_id=tenant_id, type="recurring.failed",
                                    payload={"schedule_id": schedule.id, "next_run_at": schedule.next_run_at},
                                    status="FAILED", last_error="Generation failed"))
    await session.flush()
    return created


async def run_all(session: AsyncSession, tenant_id: str | None = None) -> dict:
    tenant_ids = [tenant_id] if tenant_id else list((await session.scalars(select(Tenant.id))).all())
    result = {"tenants": len(tenant_ids), "overdue": 0, "expired_quotes": 0,
              "recurring": 0, "reminders": 0, "outbox": 0}
    for tid in tenant_ids:
        token = tenant_id_var.set(tid)
        try:
            result["overdue"] += await mark_overdue(session, tid)
            result["expired_quotes"] += await expire_quotes(session)
            result["recurring"] += await process_recurring(session, tid)
            result["reminders"] += await schedule_reminders(session, tid)
            result["outbox"] += await process_outbox(session, tid)
            await session.commit()
        finally:
            tenant_id_var.reset(token)
    return result
