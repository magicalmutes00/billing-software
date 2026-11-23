from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_tenant_id
from app.core.errors import bad_request, conflict, not_found
from app.core.security import utcnow
from app.models import HeldOrder, PosCashMovement, PosShift
from app.schemas.pos import PosCashMovementIn, PosHoldIn, PosShiftCloseIn, PosShiftOpenIn
from app.services.audit import log_audit

HOLD_TTL_HOURS = 24


# ---------- Held / parked orders ----------

async def hold_order(session: AsyncSession, data: PosHoldIn) -> HeldOrder:
    if not data.cart:
        raise bad_request("Cannot hold an empty cart")
    hold = HeldOrder(
        tenant_id=current_tenant_id(),
        cashier_id=session.info.get("actor_id"),
        label=data.label,
        cart=data.cart,
        expires_at=utcnow() + timedelta(hours=HOLD_TTL_HOURS),
    )
    session.add(hold)
    await log_audit(session, action="pos.hold", entity_type="held_order", entity_id=hold.id,
                    after={"label": data.label})
    await session.flush()
    return hold


async def list_holds(session: AsyncSession) -> list[HeldOrder]:
    now = utcnow()
    rows = list((await session.scalars(
        select(HeldOrder)
        .where(HeldOrder.tenant_id == current_tenant_id())
        .order_by(HeldOrder.created_at.desc())
    )).all())
    return [row for row in rows if row.expires_at is None or row.expires_at > now]


async def get_hold(session: AsyncSession, hold_id: str) -> HeldOrder:
    hold = await session.scalar(
        select(HeldOrder).where(HeldOrder.id == hold_id, HeldOrder.tenant_id == current_tenant_id())
    )
    if hold is None:
        raise not_found("Held order not found")
    return hold


async def resume_hold(session: AsyncSession, hold_id: str) -> dict:
    hold = await get_hold(session, hold_id)
    cart = hold.cart
    await session.delete(hold)
    await log_audit(session, action="pos.resume", entity_type="held_order", entity_id=hold_id, after={})
    await session.flush()
    return cart


async def delete_hold(session: AsyncSession, hold_id: str) -> None:
    hold = await get_hold(session, hold_id)
    await session.delete(hold)
    await session.flush()


# ---------- Shifts / cash drawer ----------

async def _open_shift(session: AsyncSession) -> PosShift | None:
    actor = session.info.get("actor_id")
    stmt = select(PosShift).where(PosShift.tenant_id == current_tenant_id(), PosShift.status == "OPEN")
    if actor:
        stmt = stmt.where(PosShift.user_id == actor)
    return await session.scalar(stmt.order_by(PosShift.opened_at.desc()))


async def open_shift(session: AsyncSession, data: PosShiftOpenIn) -> PosShift:
    existing = await _open_shift(session)
    if existing is not None:
        raise conflict("A shift is already open for this cashier")
    settings_shift_blind = data.blind_close
    shift = PosShift(
        tenant_id=current_tenant_id(),
        user_id=session.info.get("actor_id"),
        status="OPEN",
        opening_float_paise=data.opening_float_paise,
        blind_close=settings_shift_blind,
        note=data.note,
        opened_at=utcnow(),
    )
    session.add(shift)
    await log_audit(session, action="pos.shift.open", entity_type="pos_shift", entity_id=shift.id,
                    after={"opening_float_paise": data.opening_float_paise})
    await session.flush()
    return shift


async def current_shift(session: AsyncSession) -> PosShift | None:
    return await _open_shift(session)


async def _movements(session: AsyncSession, shift_id: str) -> list[PosCashMovement]:
    return list((await session.scalars(
        select(PosCashMovement)
        .where(PosCashMovement.shift_id == shift_id, PosCashMovement.tenant_id == current_tenant_id())
        .order_by(PosCashMovement.created_at)
    )).all())


def _expected_cash(shift: PosShift, movements: list[PosCashMovement]) -> int:
    total = shift.opening_float_paise
    for movement in movements:
        if movement.type in {"SALE", "CASH_IN"}:
            total += movement.amount_paise
        elif movement.type in {"REFUND", "CASH_OUT"}:
            total -= movement.amount_paise
    return total


async def cash_movement(session: AsyncSession, data: PosCashMovementIn) -> PosCashMovement:
    shift = await _open_shift(session)
    if shift is None:
        raise conflict("Open a shift before recording cash movements")
    if data.type == "NO_SALE" and data.amount_paise != 0:
        raise bad_request("A no-sale movement must have zero amount")
    movement = PosCashMovement(
        tenant_id=current_tenant_id(), shift_id=shift.id, type=data.type,
        amount_paise=data.amount_paise, note=data.note, user_id=session.info.get("actor_id"),
    )
    session.add(movement)
    await log_audit(session, action="pos.cash.movement", entity_type="pos_shift", entity_id=shift.id,
                    after={"type": data.type, "amount_paise": data.amount_paise})
    await session.flush()
    return movement


def _shift_summary(shift: PosShift, movements: list[PosCashMovement], *, blind: bool) -> dict:
    expected = _expected_cash(shift, movements)
    sales = sum(m.amount_paise for m in movements if m.type == "SALE")
    refunds = sum(m.amount_paise for m in movements if m.type == "REFUND")
    cash_in = sum(m.amount_paise for m in movements if m.type == "CASH_IN")
    cash_out = sum(m.amount_paise for m in movements if m.type == "CASH_OUT")
    summary = {
        "id": shift.id,
        "status": shift.status,
        "opened_at": shift.opened_at.isoformat() if shift.opened_at else None,
        "closed_at": shift.closed_at.isoformat() if shift.closed_at else None,
        "opening_float_paise": shift.opening_float_paise,
        "cash_sales_paise": sales,
        "refunds_paise": refunds,
        "cash_in_paise": cash_in,
        "cash_out_paise": cash_out,
        "expected_cash_paise": expected,
        "closing_count_paise": shift.closing_count_paise,
        "variance_paise": shift.variance_paise,
        "movement_count": len(movements),
        "blind_close": shift.blind_close,
    }
    if blind and shift.status == "OPEN":
        # Blind close: hide expected cash from the cashier while counting.
        summary["expected_cash_paise"] = None
    return summary


async def x_report(session: AsyncSession) -> dict:
    shift = await _open_shift(session)
    if shift is None:
        raise conflict("No open shift")
    movements = await _movements(session, shift.id)
    return _shift_summary(shift, movements, blind=False)


async def close_shift(session: AsyncSession, data: PosShiftCloseIn) -> dict:
    shift = await _open_shift(session)
    if shift is None:
        raise conflict("No open shift to close")
    movements = await _movements(session, shift.id)
    expected = _expected_cash(shift, movements)
    shift.closing_count_paise = data.closing_count_paise
    shift.expected_cash_paise = expected
    shift.variance_paise = data.closing_count_paise - expected
    shift.status = "CLOSED"
    shift.closed_at = utcnow()
    if data.note:
        shift.note = data.note
    await log_audit(session, action="pos.shift.close", entity_type="pos_shift", entity_id=shift.id,
                    after={"expected_cash_paise": expected, "variance_paise": shift.variance_paise})
    await session.flush()
    return _shift_summary(shift, movements, blind=False)


async def z_report(session: AsyncSession, shift_id: str) -> dict:
    shift = await session.scalar(
        select(PosShift).where(PosShift.id == shift_id, PosShift.tenant_id == current_tenant_id())
    )
    if shift is None:
        raise not_found("Shift not found")
    movements = await _movements(session, shift.id)
    return _shift_summary(shift, movements, blind=False)


async def list_shifts(session: AsyncSession) -> list[PosShift]:
    return list((await session.scalars(
        select(PosShift)
        .where(PosShift.tenant_id == current_tenant_id())
        .order_by(PosShift.opened_at.desc())
    )).all())
