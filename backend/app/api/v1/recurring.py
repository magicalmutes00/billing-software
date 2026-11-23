from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.db.session import get_db
from app.schemas.documents import InvoiceOut
from app.schemas.ops import RecurringCreate, RecurringOut, RecurringUpdate
from app.services import recurring_service

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("")
async def list_schedules(
    page: int = 1, limit: int = 20,
    _=Depends(require_permission("recurring.read")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    rows, total = await recurring_service.list_schedules(session, page=page, limit=limit)
    return ok([RecurringOut.model_validate(r) for r in rows], page_meta(total, page, limit))


@router.post("", status_code=201)
async def create_schedule(
    body: RecurringCreate, _=Depends(require_permission("recurring.write")), session: AsyncSession = Depends(get_db)
):
    row = await recurring_service.create_schedule(session, body)
    await session.commit()
    return ok(RecurringOut.model_validate(row))


@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: str, body: RecurringUpdate,
    _=Depends(require_permission("recurring.write")), session: AsyncSession = Depends(get_db),
):
    row = await recurring_service.update_schedule(session, schedule_id, body)
    await session.commit()
    return ok(RecurringOut.model_validate(row))


@router.post("/{schedule_id}/{action}")
async def schedule_action(
    schedule_id: str, action: str,
    _=Depends(require_permission("recurring.write")), session: AsyncSession = Depends(get_db),
):
    if action == "generate-now":
        schedule = await recurring_service.get_schedule(session, schedule_id)
        invoice = await recurring_service.generate_invoice(session, schedule)
        await session.commit()
        return ok(InvoiceOut.model_validate(invoice))
    row = await recurring_service.set_status(session, schedule_id, action.upper())
    await session.commit()
    return ok(RecurringOut.model_validate(row))
