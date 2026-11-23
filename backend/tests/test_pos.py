from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.context import tenant_id_var
from app.core.errors import ApiError
from app.core.security import decode_token
from app.models import Invoice, Payment, Permission, Role, Tenant
from app.schemas.catalog import (
    CategoryIn,
    ModifierGroupIn,
    ModifierIn,
    ProductIn,
    VariantIn,
)
from app.schemas.pos import PosItemIn, PosPaymentIn, PosSaleIn
from app.services import catalog_service, pos_service
from app.services.auth_service import create_tenant_with_owner, login, sync_all_tenants


async def seed_catalog(session):
    category = await catalog_service.create_category(session, CategoryIn(name="Tea", color="#b45309"))
    group = await catalog_service.create_modifier_group(session, ModifierGroupIn(
        name="Sugar", min_select=0, max_select=1,
        modifiers=[ModifierIn(name="Extra Sugar", price_paise=0)],
    ))
    product = await catalog_service.create_product(session, ProductIn(
        category_id=category.id,
        name="Masala Chai",
        base_price_paise=2500,
        tax_rate_pct=5,
        variants=[
            VariantIn(name="Small", price_paise=2500, is_default=True),
            VariantIn(name="Large", price_paise=4500),
        ],
        modifier_group_ids=[group["id"]],
    ))
    return category, group, product


@pytest.mark.asyncio
async def test_catalog_crud_menu_and_tenant_isolation(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    category, group, product = await seed_catalog(session)

    categories = await catalog_service.list_categories(session)
    products = await catalog_service.list_products(session)
    assert [c.name for c in categories] == ["Tea"]
    assert products[0]["name"] == "Masala Chai"
    assert products[0]["modifier_group_ids"] == [group["id"]]

    menu = await catalog_service.get_menu(session)
    assert menu[0]["name"] == "Tea"
    assert {v["name"] for v in menu[0]["products"][0]["variants"]} == {"Small", "Large"}
    assert menu[0]["products"][0]["modifier_groups"][0]["modifiers"][0]["name"] == "Extra Sugar"

    other = await create_tenant_with_owner(
        session, name="Other Shop", slug="other", email="owner@other.example.com",
        password="Password123!", full_name="Other Owner", state_code="KA",
    )
    token = tenant_id_var.set(other.id)
    try:
        assert await catalog_service.list_products(session) == []
    finally:
        tenant_id_var.reset(token)
    assert other.id != tenant.id


@pytest.mark.asyncio
async def test_pos_sale_inclusive_tax_and_receipt(db):
    session, _tenant = db
    tenant_id_var.set(_tenant.id)
    _category, _group, product = await seed_catalog(session)
    large = next(v for v in product["variants"] if v["name"] == "Large")
    sugar = (await catalog_service.list_modifier_groups(session))[0].modifiers[0]
    sale = await pos_service.create_sale(session, PosSaleIn(
        items=[PosItemIn(product_id=product["id"], variant_id=large["id"], modifier_ids=[sugar.id], qty=2)],
        discount_paise=1000,
        payment=PosPaymentIn(method="CASH", tendered_paise=10000),
    ))
    await session.commit()

    assert sale.channel == "POS"
    assert sale.number and sale.number.startswith("BILL-")
    assert sale.status == "PAID"
    assert sale.tax_mode == "INCLUSIVE"
    assert sale.subtotal_paise == 9000
    assert sale.discount_paise == 1000
    assert sale.total_paise == 8000
    assert sale.paid_paise == 8000 and sale.balance_paise == 0
    assert sale.pos_meta["method"] == "CASH"
    assert sale.pos_meta["change_paise"] == 2000
    assert sale.items[0].description == "Masala Chai (Large) + Extra Sugar"
    assert sale.items[0].product_id == product["id"]
    assert sale.items[0].variant_id == large["id"]
    assert sale.items[0].modifiers[0]["name"] == "Extra Sugar"

    receipt = await pos_service.receipt_html(session, sale.id)
    assert "Masala Chai" in receipt and "BILL-" in receipt and "TOTAL" in receipt


@pytest.mark.asyncio
async def test_pos_void_refunds_payment_and_updates_report(db):
    session, _tenant = db
    tenant_id_var.set(_tenant.id)
    _category, _group, product = await seed_catalog(session)
    small = next(v for v in product["variants"] if v["name"] == "Small")

    sale = await pos_service.create_sale(session, PosSaleIn(
        items=[PosItemIn(product_id=product["id"], variant_id=small["id"], qty=1)],
        payment=PosPaymentIn(method="UPI", reference_no="UPI-123"),
    ))
    await session.commit()

    report = await pos_service.daily_report(session, date.today())
    assert report["sales_count"] == 1
    assert report["gross_paise"] == 2500
    assert report["payment_mix"]["UPI"]["count"] == 1
    assert report["top_items"][0]["description"] == "Masala Chai (Small)"

    voided = await pos_service.void_sale(session, sale.id)
    await session.commit()
    assert voided.status == "CANCELLED"
    assert voided.balance_paise == 0
    assert voided.pos_meta["voided"] is True

    payment = await session.scalar(select(Payment).where(Payment.customer_id == sale.customer_id))
    assert payment is not None and payment.status == "REFUNDED"
    report = await pos_service.daily_report(session, date.today())
    assert report["sales_count"] == 0


@pytest.mark.asyncio
async def test_login_shop_code_and_cashier_permissions(db):
    session, tenant = db
    other = await create_tenant_with_owner(
        session, name="Second Shop", slug="second", email="owner@test.example.com",
        password="Password123!", full_name="Second Owner", state_code="KA",
    )
    await session.commit()

    with pytest.raises(ApiError) as error:
        await login(session, "owner@test.example.com", "Password123!")
    assert "shop" in str(error.value).lower()

    first = await login(session, "owner@test.example.com", "Password123!", shop="test")
    assert decode_token(first["access_token"])["tid"] == tenant.id
    second = await login(session, "owner@test.example.com", "Password123!", shop="second")
    assert decode_token(second["access_token"])["tid"] == other.id

    cashier = await session.scalar(
        select(Role).where(Role.tenant_id == tenant.id, Role.name == "CASHIER")
    )
    codes = {p.code for p in cashier.permissions}
    assert {"pos.sell", "pos.reports", "catalog.read"} <= codes
    assert "pos.void" not in codes


@pytest.mark.asyncio
async def test_sync_all_tenants_restores_new_permissions(db):
    session, tenant = db
    tenant_id_var.set(tenant.id)
    owner = await session.scalar(
        select(Role).where(Role.tenant_id == tenant.id, Role.name == "OWNER")
    )
    owner.permissions = [p for p in owner.permissions if p.code != "pos.sell"]
    await session.commit()

    await sync_all_tenants(session)
    await session.refresh(owner, ["permissions"])
    assert "pos.sell" in {p.code for p in owner.permissions}
    assert await session.scalar(select(Permission).where(Permission.code == "pos.sell")) is not None
