from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_tenant_id
from app.core.errors import conflict, not_found
from app.models import Customer, CustomerAddress, Invoice
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services.audit import log_audit


async def list_customers(
    session: AsyncSession, *, search: str | None = None, include_walkin: bool = False,
    page: int = 1, limit: int = 20
) -> tuple[list[Customer], int]:
    base = select(Customer).where(Customer.tenant_id == current_tenant_id(), Customer.deleted_at.is_(None))
    if not include_walkin:
        base = base.where(Customer.is_walkin.is_(False))
    if search:
        term = f"%{search.lower()}%"
        base = base.where(
            func.lower(Customer.display_name).like(term)
            | func.lower(Customer.legal_name).like(term)
            | func.lower(func.coalesce(Customer.email, "")).like(term)
        )
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        await session.scalars(base.options(selectinload(Customer.addresses)).order_by(Customer.created_at.desc()).offset((page - 1) * limit).limit(limit))
    ).all()
    return list(rows), total


async def get_customer(session: AsyncSession, customer_id: str) -> Customer:
    row = await session.scalar(
        select(Customer)
        .where(Customer.id == customer_id, Customer.tenant_id == current_tenant_id())
        .options(selectinload(Customer.addresses))
    )
    if row is None:
        raise not_found("Customer not found")
    return row


async def create_customer(session: AsyncSession, data: CustomerCreate) -> Customer:
    tenant_id = current_tenant_id()
    duplicate = await session.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            func.lower(Customer.display_name) == data.display_name.lower(),
            Customer.deleted_at.is_(None),
        )
    )
    if duplicate:
        raise conflict("A customer with this display name already exists")
    customer = Customer(
        tenant_id=tenant_id,
        **data.model_dump(exclude={"addresses"}),
        created_by=session.info.get("actor_id"),
        addresses=[],
    )
    session.add(customer)
    await session.flush()
    for address in data.addresses:
        customer.addresses.append(
            CustomerAddress(tenant_id=tenant_id, customer_id=customer.id, **address.model_dump())
        )
    await log_audit(session, action="customer.create", entity_type="customer", entity_id=customer.id, after={"display_name": customer.display_name})
    await session.flush()
    return customer


async def update_customer(session: AsyncSession, customer_id: str, data: CustomerUpdate) -> Customer:
    customer = await get_customer(session, customer_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    await log_audit(session, action="customer.update", entity_type="customer", entity_id=customer.id, after=data.model_dump(exclude_unset=True))
    await session.flush()
    return customer


async def delete_customer(session: AsyncSession, customer_id: str) -> None:
    customer = await get_customer(session, customer_id)
    outstanding = await session.scalar(
        select(func.coalesce(func.sum(Invoice.balance_paise), 0)).where(
            Invoice.tenant_id == customer.tenant_id,
            Invoice.customer_id == customer.id,
            Invoice.status.notin_(["PAID", "CANCELLED"]),
        )
    )
    if outstanding:
        raise conflict("Customer has outstanding invoices")
    from app.core.security import utcnow

    customer.deleted_at = utcnow().isoformat()
    await log_audit(session, action="customer.delete", entity_type="customer", entity_id=customer.id)
    await session.flush()
