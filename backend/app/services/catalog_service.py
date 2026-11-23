from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import current_tenant_id
from app.core.errors import bad_request, conflict, not_found
from app.models import (
    Modifier,
    ModifierGroup,
    Product,
    ProductCategory,
    ProductModifierGroup,
    ProductVariant,
)
from app.schemas.catalog import (
    CategoryIn,
    CategoryUpdate,
    ModifierGroupIn,
    ModifierGroupUpdate,
    ProductIn,
    ProductUpdate,
)
from app.services.audit import log_audit


def _serialize_variant(variant: ProductVariant) -> dict:
    return {
        "id": variant.id,
        "name": variant.name,
        "price_paise": variant.price_paise,
        "is_default": variant.is_default,
        "sort_order": variant.sort_order,
        "is_active": variant.is_active,
    }


def _serialize_modifier(modifier: Modifier) -> dict:
    return {
        "id": modifier.id,
        "name": modifier.name,
        "price_paise": modifier.price_paise,
        "sort_order": modifier.sort_order,
        "is_active": modifier.is_active,
    }


def _serialize_group(group: ModifierGroup, *, active_only: bool = False) -> dict:
    modifiers = [m for m in group.modifiers if m.is_active or not active_only]
    return {
        "id": group.id,
        "name": group.name,
        "min_select": group.min_select,
        "max_select": group.max_select,
        "is_required": group.is_required,
        "sort_order": group.sort_order,
        "is_active": group.is_active,
        "modifiers": [
            _serialize_modifier(m)
            for m in sorted(modifiers, key=lambda item: (item.sort_order, item.name))
        ],
    }


def _serialize_category(category: ProductCategory) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "color": category.color,
        "sort_order": category.sort_order,
        "is_active": category.is_active,
        "created_at": category.created_at,
    }


def _serialize_product(product: Product, group_ids: list[str]) -> dict:
    return {
        "id": product.id,
        "category_id": product.category_id,
        "name": product.name,
        "description": product.description,
        "base_price_paise": product.base_price_paise,
        "tax_rate_pct": product.tax_rate_pct,
        "hsn_sac": product.hsn_sac,
        "sku": product.sku,
        "barcode": product.barcode,
        "sort_order": product.sort_order,
        "is_active": product.is_active,
        "created_at": product.created_at,
        "variants": [
            _serialize_variant(v)
            for v in sorted(product.variants, key=lambda item: (item.sort_order, item.name))
        ],
        "modifier_group_ids": group_ids,
    }


# ---------------------------------------------------------------- categories

async def list_categories(session: AsyncSession) -> list[ProductCategory]:
    rows = await session.scalars(
        select(ProductCategory)
        .where(ProductCategory.tenant_id == current_tenant_id())
        .order_by(ProductCategory.sort_order, ProductCategory.name)
    )
    return list(rows.all())


async def get_category(session: AsyncSession, category_id: str) -> ProductCategory:
    row = await session.scalar(
        select(ProductCategory).where(
            ProductCategory.id == category_id,
            ProductCategory.tenant_id == current_tenant_id(),
        )
    )
    if row is None:
        raise not_found("Category not found")
    return row


async def create_category(session: AsyncSession, data: CategoryIn) -> ProductCategory:
    duplicate = await session.scalar(
        select(ProductCategory).where(
            ProductCategory.tenant_id == current_tenant_id(),
            func.lower(ProductCategory.name) == data.name.lower(),
        )
    )
    if duplicate:
        raise conflict("A category with this name already exists")
    category = ProductCategory(tenant_id=current_tenant_id(), **data.model_dump())
    session.add(category)
    await session.flush()
    await log_audit(
        session, action="catalog.category.create", entity_type="product_category",
        entity_id=category.id, after={"name": category.name},
    )
    await session.flush()
    return category


async def update_category(
    session: AsyncSession, category_id: str, data: CategoryUpdate
) -> ProductCategory:
    category = await get_category(session, category_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"].lower() != category.name.lower():
        duplicate = await session.scalar(
            select(ProductCategory).where(
                ProductCategory.tenant_id == current_tenant_id(),
                func.lower(ProductCategory.name) == payload["name"].lower(),
                ProductCategory.id != category.id,
            )
        )
        if duplicate:
            raise conflict("A category with this name already exists")
    for field, value in payload.items():
        setattr(category, field, value)
    await log_audit(
        session, action="catalog.category.update", entity_type="product_category",
        entity_id=category.id, after=payload,
    )
    await session.flush()
    return category


async def deactivate_category(session: AsyncSession, category_id: str) -> ProductCategory:
    category = await get_category(session, category_id)
    category.is_active = False
    await log_audit(
        session, action="catalog.category.deactivate", entity_type="product_category",
        entity_id=category.id,
    )
    await session.flush()
    return category


# ------------------------------------------------------------------ products

async def _group_ids_by_product(session: AsyncSession, product_ids: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    if not product_ids:
        return result
    rows = await session.scalars(
        select(ProductModifierGroup).where(
            ProductModifierGroup.tenant_id == current_tenant_id(),
            ProductModifierGroup.product_id.in_(product_ids),
        )
    )
    for link in rows.all():
        result[link.product_id].append(link.group_id)
    return result


async def list_products(session: AsyncSession) -> list[dict]:
    products = list((await session.scalars(
        select(Product)
        .where(Product.tenant_id == current_tenant_id())
        .options(selectinload(Product.variants))
        .order_by(Product.sort_order, Product.name)
    )).all())
    links = await _group_ids_by_product(session, [p.id for p in products])
    return [_serialize_product(p, links.get(p.id, [])) for p in products]


async def get_product(session: AsyncSession, product_id: str) -> Product:
    row = await session.scalar(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == current_tenant_id())
        .options(selectinload(Product.variants))
    )
    if row is None:
        raise not_found("Product not found")
    return row


async def get_product_payload(session: AsyncSession, product_id: str) -> dict:
    product = await get_product(session, product_id)
    links = await _group_ids_by_product(session, [product.id])
    return _serialize_product(product, links.get(product.id, []))


async def _validate_groups(session: AsyncSession, group_ids: list[str]) -> list[str]:
    unique = list(dict.fromkeys(group_ids))
    if not unique:
        return []
    rows = await session.scalars(
        select(ModifierGroup.id).where(
            ModifierGroup.tenant_id == current_tenant_id(), ModifierGroup.id.in_(unique)
        )
    )
    found = set(rows.all())
    missing = [gid for gid in unique if gid not in found]
    if missing:
        raise bad_request("Some add-on groups were not found")
    return unique


async def _replace_groups(session: AsyncSession, product: Product, group_ids: list[str]) -> None:
    existing = (await session.scalars(
        select(ProductModifierGroup).where(
            ProductModifierGroup.tenant_id == current_tenant_id(),
            ProductModifierGroup.product_id == product.id,
        )
    )).all()
    for link in existing:
        await session.delete(link)
    await session.flush()
    for group_id in group_ids:
        session.add(
            ProductModifierGroup(
                tenant_id=current_tenant_id(), product_id=product.id, group_id=group_id
            )
        )
    await session.flush()


def _validate_variants(variants) -> list[dict]:
    payload = [v.model_dump() for v in variants]
    names = [v["name"].strip().lower() for v in payload]
    if len(names) != len(set(names)):
        raise bad_request("Variant names must be unique within a product")
    defaults = [v for v in payload if v["is_default"]]
    if len(defaults) > 1:
        for v in payload:
            v["is_default"] = False
        defaults[0]["is_default"] = True
    elif not defaults and payload:
        payload[0]["is_default"] = True
    return payload


async def create_product(session: AsyncSession, data: ProductIn) -> dict:
    await get_category(session, data.category_id)
    duplicate = await session.scalar(
        select(Product).where(
            Product.tenant_id == current_tenant_id(),
            func.lower(Product.name) == data.name.lower(),
        )
    )
    if duplicate:
        raise conflict("A product with this name already exists")
    group_ids = await _validate_groups(session, data.modifier_group_ids)
    product = Product(
        tenant_id=current_tenant_id(),
        category_id=data.category_id,
        name=data.name,
        description=data.description,
        base_price_paise=data.base_price_paise,
        tax_rate_pct=data.tax_rate_pct,
        hsn_sac=data.hsn_sac,
        sku=data.sku,
        barcode=data.barcode,
        sort_order=data.sort_order,
        is_active=data.is_active,
        variants=[],
    )
    session.add(product)
    await session.flush()
    for variant in _validate_variants(data.variants):
        product.variants.append(
            ProductVariant(tenant_id=current_tenant_id(), product_id=product.id, **variant)
        )
    await session.flush()
    await _replace_groups(session, product, group_ids)
    await log_audit(
        session, action="catalog.product.create", entity_type="product",
        entity_id=product.id, after={"name": product.name},
    )
    await session.flush()
    return _serialize_product(product, group_ids)


async def update_product(session: AsyncSession, product_id: str, data: ProductUpdate) -> dict:
    product = await get_product(session, product_id)
    payload = data.model_dump(exclude_unset=True, exclude={"variants", "modifier_group_ids"})
    if "category_id" in payload:
        await get_category(session, payload["category_id"])
    if "name" in payload and payload["name"].lower() != product.name.lower():
        duplicate = await session.scalar(
            select(Product).where(
                Product.tenant_id == current_tenant_id(),
                func.lower(Product.name) == payload["name"].lower(),
                Product.id != product.id,
            )
        )
        if duplicate:
            raise conflict("A product with this name already exists")
    for field, value in payload.items():
        setattr(product, field, value)
    if data.variants is not None:
        variants = _validate_variants(data.variants)
        product.variants.clear()
        await session.flush()
        for variant in variants:
            product.variants.append(
                ProductVariant(tenant_id=current_tenant_id(), product_id=product.id, **variant)
            )
    group_ids = None
    if data.modifier_group_ids is not None:
        group_ids = await _validate_groups(session, data.modifier_group_ids)
        await _replace_groups(session, product, group_ids)
    await log_audit(
        session, action="catalog.product.update", entity_type="product",
        entity_id=product.id, after={k: v for k, v in payload.items() if k != "name"} | (
            {"name": payload["name"]} if "name" in payload else {}
        ),
    )
    await session.flush()
    if group_ids is None:
        group_ids = (await _group_ids_by_product(session, [product.id])).get(product.id, [])
    return _serialize_product(product, group_ids)


async def deactivate_product(session: AsyncSession, product_id: str) -> dict:
    product = await get_product(session, product_id)
    product.is_active = False
    await log_audit(
        session, action="catalog.product.deactivate", entity_type="product", entity_id=product.id
    )
    await session.flush()
    group_ids = (await _group_ids_by_product(session, [product.id])).get(product.id, [])
    return _serialize_product(product, group_ids)


# ------------------------------------------------------------ modifier groups

async def list_modifier_groups(session: AsyncSession) -> list[ModifierGroup]:
    rows = await session.scalars(
        select(ModifierGroup)
        .where(ModifierGroup.tenant_id == current_tenant_id())
        .options(selectinload(ModifierGroup.modifiers))
        .order_by(ModifierGroup.sort_order, ModifierGroup.name)
    )
    return list(rows.all())


async def get_modifier_group(session: AsyncSession, group_id: str) -> ModifierGroup:
    row = await session.scalar(
        select(ModifierGroup)
        .where(ModifierGroup.id == group_id, ModifierGroup.tenant_id == current_tenant_id())
        .options(selectinload(ModifierGroup.modifiers))
    )
    if row is None:
        raise not_found("Add-on group not found")
    return row


def _validate_group_rules(
    *, min_select: int, max_select: int, is_required: bool, modifiers: list
) -> None:
    if max_select < 1:
        raise bad_request("Maximum selections must be at least 1")
    if min_select > max_select:
        raise bad_request("Minimum selections cannot exceed the maximum")
    if is_required and not modifiers:
        raise bad_request("A required add-on group needs at least one option")
    if len(modifiers) < min_select:
        raise bad_request("Add at least as many options as the minimum selections")


async def create_modifier_group(session: AsyncSession, data: ModifierGroupIn) -> dict:
    _validate_group_rules(
        min_select=data.min_select, max_select=data.max_select,
        is_required=data.is_required, modifiers=data.modifiers,
    )
    duplicate = await session.scalar(
        select(ModifierGroup).where(
            ModifierGroup.tenant_id == current_tenant_id(),
            func.lower(ModifierGroup.name) == data.name.lower(),
        )
    )
    if duplicate:
        raise conflict("An add-on group with this name already exists")
    group = ModifierGroup(
        tenant_id=current_tenant_id(),
        name=data.name,
        min_select=data.min_select,
        max_select=data.max_select,
        is_required=data.is_required,
        sort_order=data.sort_order,
        is_active=data.is_active,
        modifiers=[],
    )
    session.add(group)
    await session.flush()
    names = [m.name.strip().lower() for m in data.modifiers]
    if len(names) != len(set(names)):
        raise bad_request("Option names must be unique within a group")
    for modifier in data.modifiers:
        group.modifiers.append(
            Modifier(tenant_id=current_tenant_id(), group_id=group.id, **modifier.model_dump())
        )
    await session.flush()
    await log_audit(
        session, action="catalog.modifier_group.create", entity_type="modifier_group",
        entity_id=group.id, after={"name": group.name},
    )
    await session.flush()
    return _serialize_group(group)


async def update_modifier_group(
    session: AsyncSession, group_id: str, data: ModifierGroupUpdate
) -> dict:
    group = await get_modifier_group(session, group_id)
    payload = data.model_dump(exclude_unset=True, exclude={"modifiers"})
    if "name" in payload and payload["name"].lower() != group.name.lower():
        duplicate = await session.scalar(
            select(ModifierGroup).where(
                ModifierGroup.tenant_id == current_tenant_id(),
                func.lower(ModifierGroup.name) == payload["name"].lower(),
                ModifierGroup.id != group.id,
            )
        )
        if duplicate:
            raise conflict("An add-on group with this name already exists")
    for field, value in payload.items():
        setattr(group, field, value)
    if data.modifiers is not None:
        names = [m.name.strip().lower() for m in data.modifiers]
        if len(names) != len(set(names)):
            raise bad_request("Option names must be unique within a group")
        group.modifiers.clear()
        await session.flush()
        for modifier in data.modifiers:
            group.modifiers.append(
                Modifier(tenant_id=current_tenant_id(), group_id=group.id, **modifier.model_dump())
            )
    _validate_group_rules(
        min_select=group.min_select, max_select=group.max_select,
        is_required=group.is_required, modifiers=group.modifiers,
    )
    await log_audit(
        session, action="catalog.modifier_group.update", entity_type="modifier_group",
        entity_id=group.id, after=payload,
    )
    await session.flush()
    return _serialize_group(group)


async def deactivate_modifier_group(session: AsyncSession, group_id: str) -> dict:
    group = await get_modifier_group(session, group_id)
    group.is_active = False
    await log_audit(
        session, action="catalog.modifier_group.deactivate", entity_type="modifier_group",
        entity_id=group.id,
    )
    await session.flush()
    return _serialize_group(group)


# --------------------------------------------------------------------- menu

async def get_menu(session: AsyncSession) -> list[dict]:
    categories = list((await session.scalars(
        select(ProductCategory)
        .where(
            ProductCategory.tenant_id == current_tenant_id(),
            ProductCategory.is_active.is_(True),
        )
        .order_by(ProductCategory.sort_order, ProductCategory.name)
    )).all())
    if not categories:
        return []
    category_ids = [c.id for c in categories]
    products = list((await session.scalars(
        select(Product)
        .where(
            Product.tenant_id == current_tenant_id(),
            Product.is_active.is_(True),
            Product.category_id.in_(category_ids),
        )
        .options(selectinload(Product.variants))
        .order_by(Product.sort_order, Product.name)
    )).all())
    product_ids = [p.id for p in products]
    links = await _group_ids_by_product(session, product_ids)
    groups = {
        g.id: g
        for g in (await session.scalars(
            select(ModifierGroup)
            .where(
                ModifierGroup.tenant_id == current_tenant_id(),
                ModifierGroup.is_active.is_(True),
            )
            .options(selectinload(ModifierGroup.modifiers))
        )).all()
    }

    by_category: dict[str, list[dict]] = defaultdict(list)
    for product in products:
        attached = [
            _serialize_group(groups[gid], active_only=True)
            for gid in links.get(product.id, [])
            if gid in groups
        ]
        by_category[product.category_id].append({
            "id": product.id,
            "category_id": product.category_id,
            "name": product.name,
            "description": product.description,
            "base_price_paise": product.base_price_paise,
            "tax_rate_pct": product.tax_rate_pct,
            "hsn_sac": product.hsn_sac,
            "sku": product.sku,
            "barcode": product.barcode,
            "sort_order": product.sort_order,
            "variants": [
                _serialize_variant(v)
                for v in sorted(product.variants, key=lambda item: (item.sort_order, item.name))
                if v.is_active
            ],
            "modifier_groups": sorted(attached, key=lambda item: (item["sort_order"], item["name"])),
        })

    return [
        {
            "id": category.id,
            "name": category.name,
            "color": category.color,
            "sort_order": category.sort_order,
            "products": by_category.get(category.id, []),
        }
        for category in categories
    ]
