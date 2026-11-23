from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.context import tenant_id_var
from app.core.errors import ApiError
from app.core.security import decode_token
from app.models import Tenant, User
from app.schemas.pos import (
    PosCashMovementIn,
    PosHoldIn,
    PosItemIn,
    PosPaymentIn,
    PosRefundIn,
    PosSaleIn,
    PosShiftCloseIn,
    PosShiftOpenIn,
)
from app.services import pos_ops_service, pos_service, report_service
from app.services.auth_service import set_pin, verify_pin
from test_pos import seed_catalog


async def _sale(session, product, variant_name="Small", **kwargs):
    variant = next(v for v in product["variants"] if v["name"] == variant_name)
    return await pos_service.create_sale(session, PosSaleIn(
        items=[PosItemIn(product_id=product["id"], variant_id=variant["id"], qty=1)],
        **kwargs,
    ))


@pytest.mark.asyncio
async def test_split_payments_mixed_tender(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    _c, _g, product = await seed_catalog(session)
    sale = await _sale(session, product, payments=[
        PosPaymentIn(method="CASH", amount_paise=1000, tendered_paise=1000),
        PosPaymentIn(method="UPI", amount_paise=1500, reference_no="UPI-X"),
    ])
    await session.commit()
    assert sale.total_paise == 2500
    assert sale.pos_meta["method"] == "SPLIT"
    assert len(sale.pos_meta["payments"]) == 2
    assert sale.paid_paise == 2500 and sale.balance_paise == 0

    with pytest.raises(ApiError):
        await _sale(session, product, payments=[
            PosPaymentIn(method="CASH", amount_paise=1000),
            PosPaymentIn(method="UPI", amount_paise=1000),
        ])  # sums to 2000, not 2500


@pytest.mark.asyncio
async def test_line_level_discount(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    row = await session.scalar(select(Tenant).where(Tenant.id == tenant.id))
    row.settings = {**(row.settings or {}), "pos_round_off": False}
    await session.commit()
    _c, _g, product = await seed_catalog(session)
    variant = next(v for v in product["variants"] if v["name"] == "Small")
    sale = await pos_service.create_sale(session, PosSaleIn(
        items=[PosItemIn(product_id=product["id"], variant_id=variant["id"], qty=1, discount_pct=10)],
        payment=PosPaymentIn(method="CASH"),
    ))
    await session.commit()
    assert sale.discount_paise == 250
    assert sale.total_paise == 2250


@pytest.mark.asyncio
async def test_held_orders_hold_and_resume(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    cart = {"items": [{"product_id": "x", "qty": 1}], "discount_paise": 0}
    hold = await pos_ops_service.hold_order(session, PosHoldIn(label="Table 1", cart=cart))
    await session.commit()
    holds = await pos_ops_service.list_holds(session)
    assert len(holds) == 1 and holds[0].label == "Table 1"
    resumed = await pos_ops_service.resume_hold(session, hold.id)
    await session.commit()
    assert resumed == cart
    assert await pos_ops_service.list_holds(session) == []


@pytest.mark.asyncio
async def test_shift_open_close_variance_and_x_report(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    owner = await session.scalar(select(User).where(User.tenant_id == tenant.id))
    session.info["actor_id"] = owner.id
    shift = await pos_ops_service.open_shift(session, PosShiftOpenIn(opening_float_paise=5000))
    await session.commit()

    await pos_ops_service.cash_movement(session, PosCashMovementIn(type="CASH_IN", amount_paise=2000))
    await pos_ops_service.cash_movement(session, PosCashMovementIn(type="CASH_OUT", amount_paise=1000))
    await session.commit()

    x = await pos_ops_service.x_report(session)
    assert x["expected_cash_paise"] == 6000  # 5000 + 2000 - 1000
    assert x["status"] == "OPEN"

    closed = await pos_ops_service.close_shift(session, PosShiftCloseIn(closing_count_paise=5800))
    await session.commit()
    assert closed["status"] == "CLOSED"
    assert closed["variance_paise"] == -200  # counted 5800 vs expected 6000

    # Reopening after a close is allowed (the previous shift is CLOSED).
    again = await pos_ops_service.open_shift(session, PosShiftOpenIn())
    assert again.status == "OPEN"


@pytest.mark.asyncio
async def test_partial_refund_reduces_report_gross(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    _c, _g, product = await seed_catalog(session)
    sale = await _sale(session, product, payment=PosPaymentIn(method="UPI"))
    await session.commit()
    refunded = await pos_service.refund_sale(session, sale.id, PosRefundIn(amount_paise=1000, reason="Wrong item"))
    await session.commit()
    assert refunded.pos_meta["refunded_paise"] == 1000
    assert refunded.paid_paise == 1500
    report = await pos_service.daily_report(session, date.today())
    assert report["gross_paise"] == 1500
    assert report["refunded_paise"] == 1000

    with pytest.raises(ApiError):
        await pos_service.refund_sale(session, sale.id, PosRefundIn(amount_paise=5000))  # exceeds refundable


@pytest.mark.asyncio
async def test_range_item_cashier_reports(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    owner = await session.scalar(select(User).where(User.tenant_id == tenant.id))
    session.info["actor_id"] = owner.id
    _c, _g, product = await seed_catalog(session)
    await _sale(session, product, payment=PosPaymentIn(method="CASH"))
    await _sale(session, product, payment=PosPaymentIn(method="UPI"))
    await session.commit()
    today = date.today()
    rng = await pos_service.range_report(session, today, today)
    assert rng["sales_count"] == 2 and rng["gross_paise"] == 5000
    assert rng["previous"]["sales_count"] == 0
    assert rng["gross_delta_paise"] == 5000
    items = await pos_service.item_report(session, today, today)
    assert items[0]["qty"] == 2
    cashiers = await pos_service.cashier_report(session, today, today)
    assert cashiers[0]["sales"] == 2


@pytest.mark.asyncio
async def test_manager_pin_approval(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    owner = await session.scalar(select(User).where(User.tenant_id == tenant.id))
    await set_pin(session, owner.id, "1234")
    await session.commit()
    result = await verify_pin(session, "1234", "pos.void")
    claims = decode_token(result["approval_token"], kind="approval")
    assert claims["perms"] == ["pos.void"] and claims["tid"] == tenant.id
    with pytest.raises(ApiError):
        await verify_pin(session, "9999", "pos.void")


@pytest.mark.asyncio
async def test_upi_qr_and_receipt_share(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    row = await session.scalar(select(Tenant).where(Tenant.id == tenant.id))
    row.settings = {**(row.settings or {}), "pos_upi_id": "chai@upi", "pos_upi_name": "Chai Corner"}
    await session.commit()
    svg = await pos_service.upi_qr_svg(session, 2500, "BILL-1")
    assert svg.startswith("<") and "svg" in svg

    _c, _g, product = await seed_catalog(session)
    sale = await _sale(session, product, payment=PosPaymentIn(method="CASH"))
    await session.commit()
    share = await pos_service.receipt_share_token(session, sale.id)
    claims = decode_token(share["token"], kind="receipt")
    assert claims["sub"] == sale.id and claims["tid"] == tenant.id


@pytest.mark.asyncio
async def test_multi_shop_summary(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    owner = await session.scalar(select(User).where(User.tenant_id == tenant.id))
    _c, _g, product = await seed_catalog(session)
    await _sale(session, product, payment=PosPaymentIn(method="CASH"))
    await session.commit()
    shops = await report_service.shops_summary(session, owner.id)
    assert len(shops) == 1
    assert shops[0]["today_sales"] == 1 and shops[0]["today_gross_paise"] == 2500
