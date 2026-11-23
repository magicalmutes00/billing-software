from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.core.context import current_tenant_id
from app.db.session import get_db
from app.models.ops import AuditLog
from app.schemas.ops import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit(
    action: str | None = None, entity_type: str | None = None, page: int = 1, limit: int = 20,
    _=Depends(require_permission("audit.read")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    where = [AuditLog.tenant_id == current_tenant_id()]
    if action:
        where.append(func.lower(AuditLog.action).like(f"%{action.lower()}%"))
    if entity_type:
        where.append(AuditLog.entity_type == entity_type)
    stmt = select(AuditLog).where(*where)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.order_by(AuditLog.created_at.desc())
                                  .offset((page - 1) * limit).limit(limit))).all()
    return ok([AuditOut.model_validate(r) for r in rows], page_meta(total, page, limit))
