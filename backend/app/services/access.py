from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.core.context import current_tenant_id
from app.models import Customer, Invoice


async def get_customer(session: AsyncSession, customer_id: str) -> Customer:
    row = await session.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == current_tenant_id())
    )
    if row is None:
        raise not_found("Customer not found")
    return row


async def get_invoice(session: AsyncSession, invoice_id: str) -> Invoice:
    row = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == current_tenant_id())
    )
    if row is None:
        raise not_found("Invoice not found")
    return row


def snapshot(row: object, fields: list[str]) -> dict:
    return {field: getattr(row, field) for field in fields if hasattr(row, field)}
