from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_tenant_id
from app.core.errors import bad_request, conflict, not_found
from app.models import RecurringSchedule
from app.schemas.ops import RecurringCreate, RecurringUpdate
from app.services.access import get_customer
from app.services.audit import log_audit


def _add_period(start: date, frequency: str, interval: int) -> date:
    if frequency == "MONTHLY":
        month = start.month - 1 + interval
        year = start.year + month // 12
        month = month % 12 + 1
        day = min(start.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                              31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day)
    if frequency == "QUARTERLY":
        return _add_period(start, "MONTHLY", 3 * interval)
    return date(start.year + interval, start.month, start.day)


def _period_label(day: date, frequency: str) -> str:
    if frequency == "YEARLY":
        return str(day.year)
    if frequency == "QUARTERLY":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    return f"{day.year}-{day.month:02d}"


async def list_schedules(session: AsyncSession, page: int = 1, limit: int = 20) -> tuple[list[RecurringSchedule], int]:
    stmt = select(RecurringSchedule).where(RecurringSchedule.tenant_id == current_tenant_id())
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.order_by(RecurringSchedule.created_at.desc())
                                  .offset((page - 1) * limit).limit(limit))).all()
    return list(rows), total


async def get_schedule(session: AsyncSession, schedule_id: str) -> RecurringSchedule:
    row = await session.scalar(
        select(RecurringSchedule).where(RecurringSchedule.id == schedule_id,
                                        RecurringSchedule.tenant_id == current_tenant_id())
    )
    if row is None:
        raise not_found("Recurring schedule not found")
    return row


async def create_schedule(session: AsyncSession, data: RecurringCreate) -> RecurringSchedule:
    tenant_id = current_tenant_id()
    await get_customer(session, data.customer_id)
    if not data.template.get("items"):
        raise bad_request("Template must contain at least one item")
    schedule = RecurringSchedule(
        tenant_id=tenant_id,
        customer_id=data.customer_id,
        name=data.name,
        frequency=data.frequency,
        interval=data.interval,
        start_date=data.start_date,
        end_date=data.end_date,
        next_run_at=data.next_run_at or data.start_date,
        template=data.template,
        created_by=session.info.get("actor_id"),
        status="ACTIVE",
    )
    session.add(schedule)
    await log_audit(session, action="recurring.create", entity_type="recurring", entity_id=schedule.id,
                    after={"name": schedule.name})
    await session.flush()
    return schedule


async def update_schedule(session: AsyncSession, schedule_id: str, data: RecurringUpdate) -> RecurringSchedule:
    schedule = await get_schedule(session, schedule_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    await log_audit(session, action="recurring.update", entity_type="recurring", entity_id=schedule.id)
    await session.flush()
    return schedule


async def set_status(session: AsyncSession, schedule_id: str, status: str) -> RecurringSchedule:
    schedule = await get_schedule(session, schedule_id)
    if status == "PAUSE":
        schedule.status = "PAUSED"
    elif status == "RESUME":
        schedule.status = "ACTIVE"
    elif status == "CANCEL":
        schedule.status = "CANCELLED"
    else:
        raise bad_request("Unsupported schedule action")
    await log_audit(session, action=f"recurring.{status.lower()}", entity_type="recurring", entity_id=schedule.id)
    await session.flush()
    return schedule


async def generate_invoice(session: AsyncSession, schedule: RecurringSchedule, when: date | None = None) -> object:
    from app.schemas.documents import InvoiceCreate
    from app.services.invoice_service import create_invoice

    run_date = when or date.fromisoformat(schedule.next_run_at)
    period = _period_label(run_date, schedule.frequency)
    if schedule.last_period == period and schedule.last_invoice_id:
        raise conflict(f"Invoice for {period} was already generated")
    template = dict(schedule.template)
    items = template.pop("items")
    payload = InvoiceCreate.model_validate({
        "customer_id": schedule.customer_id,
        "issue_date": run_date.isoformat(),
        "items": items,
        **template,
    })
    invoice = await create_invoice(session, payload)
    schedule.last_invoice_id = invoice.id
    schedule.last_period = period
    schedule.next_run_at = _add_period(run_date, schedule.frequency, schedule.interval).isoformat()
    await log_audit(session, action="recurring.generate", entity_type="recurring", entity_id=schedule.id,
                    after={"invoice_id": invoice.id})
    await session.flush()
    return invoice
