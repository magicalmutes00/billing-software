from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_actor_id, current_tenant_id
from app.models.ops import AuditLog


async def log_audit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=current_tenant_id(),
            actor_id=current_actor_id(),
            actor_type="USER",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            ip=ip,
            user_agent=user_agent,
        )
    )
