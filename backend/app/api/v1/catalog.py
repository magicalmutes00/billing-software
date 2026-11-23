from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.api.v1.helpers import ok
from app.db.session import get_db
from app.schemas.catalog import (
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    ModifierGroupIn,
    ModifierGroupOut,
    ModifierGroupUpdate,
    ProductIn,
    ProductOut,
    ProductUpdate,
)
from app.services import catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/categories")
async def list_categories(
    _=Depends(require_permission("catalog.read")), session: AsyncSession = Depends(get_db)
):
    rows = await catalog_service.list_categories(session)
    return ok([CategoryOut.model_validate(row) for row in rows])


@router.post("/categories", status_code=201)
async def create_category(
    body: CategoryIn, _=Depends(require_permission("catalog.write")),
    session: AsyncSession = Depends(get_db),
):
    category = await catalog_service.create_category(session, body)
    await session.commit()
    return ok(CategoryOut.model_validate(category))


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: str, body: CategoryUpdate,
    _=Depends(require_permission("catalog.write")), session: AsyncSession = Depends(get_db),
):
    category = await catalog_service.update_category(session, category_id, body)
    await session.commit()
    return ok(CategoryOut.model_validate(category))


@router.delete("/categories/{category_id}")
async def deactivate_category(
    category_id: str, _=Depends(require_permission("catalog.write")),
    session: AsyncSession = Depends(get_db),
):
    category = await catalog_service.deactivate_category(session, category_id)
    await session.commit()
    return ok(CategoryOut.model_validate(category))


@router.get("/products")
async def list_products(
    _=Depends(require_permission("catalog.read")), session: AsyncSession = Depends(get_db)
):
    return ok(await catalog_service.list_products(session))


@router.post("/products", status_code=201)
async def create_product(
    body: ProductIn, _=Depends(require_permission("catalog.write")),
    session: AsyncSession = Depends(get_db),
):
    product = await catalog_service.create_product(session, body)
    await session.commit()
    return ok(product)


@router.get("/products/{product_id}")
async def get_product(
    product_id: str, _=Depends(require_permission("catalog.read")),
    session: AsyncSession = Depends(get_db),
):
    return ok(await catalog_service.get_product_payload(session, product_id))


@router.patch("/products/{product_id}")
async def update_product(
    product_id: str, body: ProductUpdate,
    _=Depends(require_permission("catalog.write")), session: AsyncSession = Depends(get_db),
):
    product = await catalog_service.update_product(session, product_id, body)
    await session.commit()
    return ok(product)


@router.delete("/products/{product_id}")
async def deactivate_product(
    product_id: str, _=Depends(require_permission("catalog.write")),
    session: AsyncSession = Depends(get_db),
):
    product = await catalog_service.deactivate_product(session, product_id)
    await session.commit()
    return ok(product)


@router.get("/modifier-groups")
async def list_modifier_groups(
    _=Depends(require_permission("catalog.read")), session: AsyncSession = Depends(get_db)
):
    rows = await catalog_service.list_modifier_groups(session)
    return ok([ModifierGroupOut.model_validate(row) for row in rows])


@router.post("/modifier-groups", status_code=201)
async def create_modifier_group(
    body: ModifierGroupIn, _=Depends(require_permission("catalog.write")),
    session: AsyncSession = Depends(get_db),
):
    group = await catalog_service.create_modifier_group(session, body)
    await session.commit()
    return ok(group)


@router.patch("/modifier-groups/{group_id}")
async def update_modifier_group(
    group_id: str, body: ModifierGroupUpdate,
    _=Depends(require_permission("catalog.write")), session: AsyncSession = Depends(get_db),
):
    group = await catalog_service.update_modifier_group(session, group_id, body)
    await session.commit()
    return ok(group)


@router.delete("/modifier-groups/{group_id}")
async def deactivate_modifier_group(
    group_id: str, _=Depends(require_permission("catalog.write")),
    session: AsyncSession = Depends(get_db),
):
    group = await catalog_service.deactivate_modifier_group(session, group_id)
    await session.commit()
    return ok(group)
