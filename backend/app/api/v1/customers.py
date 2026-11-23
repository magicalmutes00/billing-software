from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.core.context import current_tenant_id
from app.db.session import get_db
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
async def list_customers(
    search: str | None = None, page: int = 1, limit: int = 20,
    _=Depends(require_permission("customers.read")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    rows, total = await customer_service.list_customers(session, search=search, page=page, limit=limit)
    from sqlalchemy import func, select
    from app.models import Invoice

    items = []
    for row in rows:
        outstanding = await session.scalar(
            select(func.coalesce(func.sum(Invoice.balance_paise), 0)).where(
                Invoice.tenant_id == current_tenant_id(), Invoice.customer_id == row.id,
                Invoice.status.notin_(["PAID", "CANCELLED"]),
            )
        ) or 0
        items.append(CustomerOut.model_validate(row).model_copy(update={"outstanding_paise": outstanding}))
    return ok(items, page_meta(total, page, limit))


@router.post("", status_code=201)
async def create_customer(
    body: CustomerCreate,
    _=Depends(require_permission("customers.write")),
    session: AsyncSession = Depends(get_db),
):
    customer = await customer_service.create_customer(session, body)
    await session.commit()
    return ok(CustomerOut.model_validate(customer))


@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    _=Depends(require_permission("customers.read")),
    session: AsyncSession = Depends(get_db),
):
    return ok(CustomerOut.model_validate(await customer_service.get_customer(session, customer_id)))


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: str, body: CustomerUpdate,
    _=Depends(require_permission("customers.write")),
    session: AsyncSession = Depends(get_db),
):
    customer = await customer_service.update_customer(session, customer_id, body)
    await session.commit()
    return ok(CustomerOut.model_validate(customer))


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: str,
    _=Depends(require_permission("customers.write")),
    session: AsyncSession = Depends(get_db),
):
    await customer_service.delete_customer(session, customer_id)
    await session.commit()
