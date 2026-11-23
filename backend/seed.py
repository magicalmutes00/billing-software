"""Seed demo tenants: a billing workspace and two retail counter shops."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.core.context import tenant_id_var
from app.core.security import hash_password
from app.db.session import AdminSessionLocal, init_db, set_tenant_context
from app.models import Role, Tenant, User
from app.schemas.catalog import CategoryIn, ModifierGroupIn, ModifierIn, ProductIn, VariantIn
from app.schemas.customer import AddressIn, CustomerCreate
from app.schemas.documents import InvoiceCreate, ItemIn, QuoteCreate
from app.schemas.ops import RecurringCreate
from app.schemas.payments import AllocationIn, PaymentCreate
from app.services import (
    catalog_service,
    credit_note_service,
    customer_service,
    invoice_service,
    payment_service,
    quote_service,
    recurring_service,
)
from app.services.auth_service import create_tenant_with_owner, sync_all_tenants

RETAIL_PASSWORD = "Password123!"


async def _seed_acme(session) -> None:
    existing = await session.scalar(select(Tenant).where(Tenant.slug == "acme"))
    if existing:
        print("Billing demo tenant already seeded.")
        return
    tenant = await create_tenant_with_owner(
        session,
        name="Acme Studio",
        slug="acme",
        email="owner@acme.example.com",
        password="Password123!",
        full_name="Aarav Mehta",
        legal_name="Acme Studio LLP",
        gstin="29ABCDE1234F1Z5",
        state_code="KA",
        address_line1="12 MG Road",
        city="Bengaluru",
        pincode="560001",
        settings={"invoice_prefix": "INV", "payment_terms_days": 15, "tax_mode": "EXCLUSIVE"},
    )
    token = tenant_id_var.set(tenant.id)
    await set_tenant_context(session, tenant.id)
    try:
        c1 = await customer_service.create_customer(session, CustomerCreate(
            legal_name="Bengaluru Enterprises Pvt Ltd",
            display_name="Bengaluru Enterprises",
            gstin="29AABCI1234K1Z2",
            tax_type="REGISTERED",
            state_code="KA",
            email="billing@bengaluru.example.com",
            payment_terms_days=15,
            addresses=[AddressIn(line1="88 Church Street", city="Bengaluru", state_code="KA", pincode="560001")],
        ))
        c2 = await customer_service.create_customer(session, CustomerCreate(
            legal_name="Chennai Traders",
            display_name="Chennai Traders",
            gstin="33AABCI9876K1Z9",
            tax_type="REGISTERED",
            state_code="TN",
            email="accounts@chennai.example.com",
            payment_terms_days=30,
            addresses=[AddressIn(line1="4 Mount Road", city="Chennai", state_code="TN", pincode="600002")],
        ))
        items = [
            ItemIn(description="Brand identity design", hsn_sac="998231", qty=1, unit_price_paise=7500000, tax_rate_pct=18),
            ItemIn(description="Website UI kit", hsn_sac="998336", qty=2, unit_price_paise=2500000, discount_paise=50000, tax_rate_pct=18),
        ]
        invoice = await invoice_service.create_invoice(session, InvoiceCreate(
            customer_id=c1.id, issue_date=date.today() - timedelta(days=10), items=items,
            notes="Thank you for your business.",
        ))
        await invoice_service.send_invoice(session, invoice.id)
        await payment_service.create_payment(session, PaymentCreate(
            customer_id=c1.id, amount_paise=5000000, method="BANK", reference_no="NEFT-20261120-001",
            allocations=[AllocationIn(invoice_id=invoice.id, amount_paise=5000000)],
        ))
        interstate = await invoice_service.create_invoice(session, InvoiceCreate(
            customer_id=c2.id, issue_date=date.today() - timedelta(days=3),
            items=[ItemIn(description="Motion graphics package", hsn_sac="998331", qty=1,
                          unit_price_paise=4500000, tax_rate_pct=18)],
        ))
        await invoice_service.send_invoice(session, interstate.id)
        quote = await quote_service.create_quote(session, QuoteCreate(
            customer_id=c2.id, issue_date=date.today(),
            valid_until=date.today() + timedelta(days=30),
            items=[ItemIn(description="Quarterly marketing retainer", qty=3,
                          unit_price_paise=3000000, tax_rate_pct=18)],
        ))
        await quote_service.send_quote(session, quote.id)
        await recurring_service.create_schedule(session, RecurringCreate(
            customer_id=c1.id, name="Monthly retainer", frequency="MONTHLY",
            start_date=date.today().replace(day=1).isoformat(),
            template={"items": [ItemIn(description="Monthly design retainer", qty=1,
                                        unit_price_paise=2500000, tax_rate_pct=18).model_dump()]},
        ))
        await session.commit()
        print(f"Seeded billing tenant '{tenant.name}'. Login: owner@acme.example.com / Password123!")
    finally:
        tenant_id_var.reset(token)


def _price(paise: int, multiplier: float) -> int:
    return int(round(paise * multiplier / 100.0)) * 100


async def _seed_catalog(session, *, multiplier: float, extra_tea: bool = False) -> None:
    categories = {}
    for name, color, order in (
        ("Tea", "#b45309", 1),
        ("Coffee", "#78350f", 2),
        ("Cool Drinks", "#0369a1", 3),
        ("Snacks", "#15803d", 4),
    ):
        categories[name] = await catalog_service.create_category(
            session, CategoryIn(name=name, color=color, sort_order=order)
        )

    sugar = await catalog_service.create_modifier_group(session, ModifierGroupIn(
        name="Sugar", min_select=0, max_select=1, sort_order=1,
        modifiers=[
            ModifierIn(name="Extra Sugar", price_paise=0, sort_order=1),
            ModifierIn(name="Less Sugar", price_paise=0, sort_order=2),
        ],
    ))
    milk = await catalog_service.create_modifier_group(session, ModifierGroupIn(
        name="Milk", min_select=0, max_select=1, sort_order=2,
        modifiers=[
            ModifierIn(name="Extra Milk", price_paise=_price(500, multiplier), sort_order=1),
            ModifierIn(name="Almond Milk", price_paise=_price(1500, multiplier), sort_order=2),
        ],
    ))
    coffee_extras = await catalog_service.create_modifier_group(session, ModifierGroupIn(
        name="Coffee extras", min_select=0, max_select=2, sort_order=3,
        modifiers=[
            ModifierIn(name="Extra Shot", price_paise=_price(2000, multiplier), sort_order=1),
            ModifierIn(name="Extra Ice", price_paise=0, sort_order=2),
        ],
    ))
    sandwich_extras = await catalog_service.create_modifier_group(session, ModifierGroupIn(
        name="Sandwich add-ons", min_select=0, max_select=2, sort_order=4,
        modifiers=[
            ModifierIn(name="Cheese", price_paise=_price(2000, multiplier), sort_order=1),
            ModifierIn(name="Grilled", price_paise=_price(1000, multiplier), sort_order=2),
        ],
    ))

    async def product(
        name: str, category: str, base: int, tax: float, variants: list[tuple[str, int]],
        groups: list[str], description: str | None = None,
    ) -> None:
        await catalog_service.create_product(session, ProductIn(
            category_id=categories[category].id,
            name=name,
            description=description,
            base_price_paise=_price(base, multiplier),
            tax_rate_pct=tax,
            hsn_sac="996331" if category in {"Tea", "Coffee"} else None,
            sort_order=len(variants) + 1,
            variants=[
                VariantIn(
                    name=variant_name,
                    price_paise=_price(price, multiplier),
                    is_default=index == 0,
                    sort_order=index + 1,
                )
                for index, (variant_name, price) in enumerate(variants)
            ],
            modifier_group_ids=groups,
        ))

    await product("Masala Chai", "Tea", 2500, 5,
                  [("Small", 2500), ("Medium", 3500), ("Large", 4500)],
                  [sugar["id"], milk["id"]], "House masala, brewed fresh all day.")
    await product("Filter Coffee", "Coffee", 3000, 5,
                  [("Small", 3000), ("Large", 4000)],
                  [sugar["id"], milk["id"]], "South Indian filter decoction with hot milk.")
    await product("Cold Coffee", "Coffee", 6000, 5,
                  [("Regular", 6000), ("Large", 8000)],
                  [sugar["id"], coffee_extras["id"]], "Chilled coffee blended with milk.")
    if extra_tea:
        await product("Kesari Chai", "Tea", 3000, 5,
                      [("Small", 3000), ("Large", 4000)],
                      [sugar["id"], milk["id"]], "Saffron and cardamom tea.")
    await product("Fresh Lime Soda", "Cool Drinks", 4000, 12, [], [], "Sweet, salted or mixed.")
    await product("Cola", "Cool Drinks", 3000, 28, [], [], "Chilled 300 ml bottle.")
    await product("Orange Juice", "Cool Drinks", 5000, 12, [], [], "Fresh pressed, no added sugar.")
    await product("Veg Puff", "Snacks", 3000, 5, [], [], "Flaky puff with spiced vegetables.")
    await product("Samosa", "Snacks", 2000, 5, [], [], "Two pieces, served hot.")
    await product("Veg Sandwich", "Snacks", 5000, 5, [],
                  [sandwich_extras["id"]], "Grilled sandwich with mint chutney.")
    await product("Masala Fries", "Snacks", 6000, 5, [], [], "Crispy fries with house masala.")


async def _seed_shop(
    session, *, name: str, slug: str, city: str, address: str, phone: str,
    multiplier: float = 1.0, extra_tea: bool = False, seed_cashier: bool = False,
) -> None:
    existing = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if existing is None:
        tenant = await create_tenant_with_owner(
            session,
            name=name,
            slug=slug,
            email="owner@chaicorner.example.com",
            password=RETAIL_PASSWORD,
            full_name="Meera Rao",
            legal_name=f"{name} LLP",
            gstin="29AACCC1234D1Z7",
            state_code="KA",
            address_line1=address,
            city=city,
            pincode="560001",
            settings={
                "invoice_prefix": "INV",
                "pos_receipt_header": name,
                "pos_receipt_footer": "Thank you! Visit again.",
                "pos_phone": phone,
                "pos_show_gstin": True,
                "pos_tax_mode": "INCLUSIVE",
                "pos_round_off": True,
            },
        )
        print(f"Seeded shop '{tenant.name}'. Shop code: {slug}")
    else:
        tenant = existing
        print(f"Shop '{name}' already seeded.")

    token = tenant_id_var.set(tenant.id)
    await set_tenant_context(session, tenant.id)
    try:
        has_catalog = await catalog_service.list_categories(session)
        if not has_catalog:
            await _seed_catalog(session, multiplier=multiplier, extra_tea=extra_tea)
        if seed_cashier:
            cashier = await session.scalar(
                select(User).where(
                    User.tenant_id == tenant.id,
                    User.email == "cashier@chaicorner.example.com",
                )
            )
            if cashier is None:
                role = await session.scalar(
                    select(Role).where(Role.tenant_id == tenant.id, Role.name == "CASHIER")
                )
                if role is not None:
                    session.add(User(
                        tenant_id=tenant.id,
                        email="cashier@chaicorner.example.com",
                        full_name="Ravi Kumar",
                        password_hash=hash_password(RETAIL_PASSWORD),
                        roles=[role],
                    ))
                    await session.flush()
                    print("Seeded cashier: cashier@chaicorner.example.com / Password123!")
        await session.commit()
    finally:
        tenant_id_var.reset(token)


async def main() -> None:
    await init_db()
    async with AdminSessionLocal() as session:
        await sync_all_tenants(session)
        await _seed_acme(session)
        await _seed_shop(
            session,
            name="Chai Corner — Indiranagar",
            slug="chai-indiranagar",
            city="Bengaluru",
            address="100 Feet Road, Indiranagar",
            phone="+91 80 4123 4567",
            seed_cashier=True,
        )
        await _seed_shop(
            session,
            name="Chai Corner — Koramangala",
            slug="chai-koramangala",
            city="Bengaluru",
            address="5th Block, Koramangala",
            phone="+91 80 4123 4568",
            multiplier=1.1,
            extra_tea=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
