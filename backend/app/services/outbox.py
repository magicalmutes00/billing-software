from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_tenant_id
from app.models.ops import OutboxEvent


async def enqueue(session: AsyncSession, event_type: str, payload: dict | None = None) -> OutboxEvent:
    event = OutboxEvent(
        tenant_id=current_tenant_id(), type=event_type, payload=payload or {}, status="PENDING"
    )
    session.add(event)
    await session.flush()
    return event
