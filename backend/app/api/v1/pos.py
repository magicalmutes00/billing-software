from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.db.session import get_db
from app.schemas.catalog import MenuCategory
from app.schemas.documents import InvoiceOut
from app.schemas.pos import (
    PosCashMovementIn,
    PosHoldIn,
    PosRefundIn,
    PosSaleIn,
    PosShiftCloseIn,
    PosShiftOpenIn,
    PosVoidIn,
)
from app.services import catalog_service, pos_ops_service, pos_service

router = APIRouter(prefix="/pos", tags=["pos"])


@router.get("/menu")
async def menu(_=Depends(require_permission("pos.sell")), session: AsyncSession = Depends(get_db)):
    return ok([MenuCategory.model_validate(row) for row in await catalog_service.get_menu(session)])


@router.post("/sales", status_code=201)
async def create_sale(
    body: PosSaleIn, _=Depends(require_permission("pos.sell")),
    session: AsyncSession = Depends(get_db),
):
    sale = await pos_service.create_sale(session, body)
    await session.commit()
    return ok(InvoiceOut.model_validate(sale))


@router.get("/sales")
async def list_sales(
    date_from: date | None = None, date_to: date | None = None,
    payment: str | None = None, search: str | None = None,
    page: int = 1, limit: int = 20,
    _=Depends(require_permission("pos.reports")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    rows, total = await pos_service.list_sales(
        session, date_from=date_from, date_to=date_to, payment=payment,
        search=search, page=page, limit=limit,
    )
    return ok([InvoiceOut.model_validate(row) for row in rows], page_meta(total, page, limit))


@router.get("/sales/export")
async def export_sales(
    date_from: date | None = None, date_to: date | None = None,
    _=Depends(require_permission("pos.reports")), session: AsyncSession = Depends(get_db),
):
    import csv
    import io

    start = date_from or date.today()
    end = date_to or start
    rows = await pos_service._pos_rows(session, start, end)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Bill", "Date", "Cashier", "Payment", "Subtotal", "Discount", "Tax", "Refunded", "Total", "Status"])
    for row in rows:
        meta = row.pos_meta or {}
        writer.writerow([
            row.number, row.issue_date.isoformat(), meta.get("cashier") or "",
            meta.get("method") or "", row.subtotal_paise, row.discount_paise, row.tax_paise,
            int(meta.get("refunded_paise", 0)), row.total_paise, row.status,
        ])
    return Response(
        content=buffer.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="counter-sales-{start}-to-{end}.csv"'},
    )


@router.get("/sales/{sale_id}")
async def get_sale(
    sale_id: str, _=Depends(require_permission("pos.reports")),
    session: AsyncSession = Depends(get_db),
):
    return ok(InvoiceOut.model_validate(await pos_service.get_sale(session, sale_id)))


@router.get("/sales/{sale_id}/receipt", response_class=HTMLResponse)
async def sale_receipt(
    sale_id: str, _=Depends(require_permission("pos.reports")),
    session: AsyncSession = Depends(get_db),
):
    return HTMLResponse(await pos_service.receipt_html(session, sale_id))


@router.post("/sales/{sale_id}/void")
async def void_sale(
    sale_id: str, body: PosVoidIn,
    _=Depends(require_permission("pos.void")), session: AsyncSession = Depends(get_db),
):
    sale = await pos_service.void_sale(session, sale_id, body.reason)
    await session.commit()
    return ok(InvoiceOut.model_validate(sale))


@router.post("/sales/{sale_id}/refund")
async def refund_sale(
    sale_id: str, body: PosRefundIn,
    _=Depends(require_permission("pos.void")), session: AsyncSession = Depends(get_db),
):
    sale = await pos_service.refund_sale(session, sale_id, body)
    await session.commit()
    return ok(InvoiceOut.model_validate(sale))


@router.post("/sales/{sale_id}/share-token")
async def share_token(
    sale_id: str, _=Depends(require_permission("pos.reports")),
    session: AsyncSession = Depends(get_db),
):
    return ok(await pos_service.receipt_share_token(session, sale_id))


@router.get("/upi-qr")
async def upi_qr(
    amount_paise: int, tn: str = "",
    _=Depends(require_permission("pos.sell")), session: AsyncSession = Depends(get_db),
):
    svg = await pos_service.upi_qr_svg(session, amount_paise, tn)
    return Response(content=svg, media_type="image/svg+xml")


# ---------- Held / parked orders ----------

@router.post("/holds", status_code=201)
async def hold_order(
    body: PosHoldIn, _=Depends(require_permission("pos.sell")),
    session: AsyncSession = Depends(get_db),
):
    hold = await pos_ops_service.hold_order(session, body)
    await session.commit()
    return ok({"id": hold.id, "label": hold.label, "cart": hold.cart, "created_at": hold.created_at})


@router.get("/holds")
async def list_holds(_=Depends(require_permission("pos.sell")), session: AsyncSession = Depends(get_db)):
    rows = await pos_ops_service.list_holds(session)
    return ok([
        {"id": row.id, "label": row.label, "cart": row.cart, "created_at": row.created_at}
        for row in rows
    ])


@router.post("/holds/{hold_id}/resume")
async def resume_hold(
    hold_id: str, _=Depends(require_permission("pos.sell")),
    session: AsyncSession = Depends(get_db),
):
    cart = await pos_ops_service.resume_hold(session, hold_id)
    await session.commit()
    return ok(cart)


@router.delete("/holds/{hold_id}")
async def delete_hold(
    hold_id: str, _=Depends(require_permission("pos.sell")),
    session: AsyncSession = Depends(get_db),
):
    await pos_ops_service.delete_hold(session, hold_id)
    await session.commit()
    return ok({"deleted": True})


# ---------- Shifts / cash drawer ----------

@router.post("/shifts/open", status_code=201)
async def open_shift(
    body: PosShiftOpenIn, _=Depends(require_permission("pos.sell")),
    session: AsyncSession = Depends(get_db),
):
    shift = await pos_ops_service.open_shift(session, body)
    await session.commit()
    return ok({"id": shift.id, "status": shift.status, "opening_float_paise": shift.opening_float_paise})


@router.get("/shifts/current")
async def current_shift(_=Depends(require_permission("pos.sell")), session: AsyncSession = Depends(get_db)):
    shift = await pos_ops_service.current_shift(session)
    if shift is None:
        return ok(None)
    return ok({"id": shift.id, "status": shift.status, "opening_float_paise": shift.opening_float_paise,
               "opened_at": shift.opened_at, "blind_close": shift.blind_close})


@router.post("/shifts/close")
async def close_shift(
    body: PosShiftCloseIn, _=Depends(require_permission("pos.sell")),
    session: AsyncSession = Depends(get_db),
):
    summary = await pos_ops_service.close_shift(session, body)
    await session.commit()
    return ok(summary)


@router.post("/shifts/cash-movement", status_code=201)
async def cash_movement(
    body: PosCashMovementIn, _=Depends(require_permission("pos.sell")),
    session: AsyncSession = Depends(get_db),
):
    movement = await pos_ops_service.cash_movement(session, body)
    await session.commit()
    return ok({"id": movement.id, "type": movement.type, "amount_paise": movement.amount_paise})


@router.get("/shifts/x-report")
async def x_report(_=Depends(require_permission("pos.sell")), session: AsyncSession = Depends(get_db)):
    return ok(await pos_ops_service.x_report(session))


@router.get("/shifts/{shift_id}/z-report")
async def z_report(
    shift_id: str, _=Depends(require_permission("pos.reports")),
    session: AsyncSession = Depends(get_db),
):
    return ok(await pos_ops_service.z_report(session, shift_id))


@router.get("/shifts")
async def list_shifts(_=Depends(require_permission("pos.reports")), session: AsyncSession = Depends(get_db)):
    rows = await pos_ops_service.list_shifts(session)
    return ok([
        {"id": row.id, "status": row.status, "opened_at": row.opened_at, "closed_at": row.closed_at,
         "opening_float_paise": row.opening_float_paise, "variance_paise": row.variance_paise}
        for row in rows
    ])


# ---------- Reports ----------

@router.get("/reports/daily")
async def daily_report(
    day: date | None = None, _=Depends(require_permission("pos.reports")),
    session: AsyncSession = Depends(get_db),
):
    return ok(await pos_service.daily_report(session, day or date.today()))


@router.get("/reports/range")
async def range_report(
    date_from: date, date_to: date,
    _=Depends(require_permission("pos.reports")), session: AsyncSession = Depends(get_db),
):
    return ok(await pos_service.range_report(session, date_from, date_to))


@router.get("/reports/items")
async def item_report(
    date_from: date, date_to: date,
    _=Depends(require_permission("pos.reports")), session: AsyncSession = Depends(get_db),
):
    return ok(await pos_service.item_report(session, date_from, date_to))


@router.get("/reports/cashiers")
async def cashier_report(
    date_from: date, date_to: date,
    _=Depends(require_permission("pos.reports")), session: AsyncSession = Depends(get_db),
):
    return ok(await pos_service.cashier_report(session, date_from, date_to))
