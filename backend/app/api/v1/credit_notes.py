from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.db.session import get_db
from app.schemas.payments import CreditNoteCreate, CreditNoteOut
from app.services import credit_note_service

router = APIRouter(prefix="/credit-notes", tags=["credit-notes"])


class ApplyIn(BaseModel):
    invoice_id: str | None = None
    amount_paise: int | None = None


@router.get("")
async def list_notes(
    page: int = 1, limit: int = 20,
    _=Depends(require_permission("credit_notes.read")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    rows, total = await credit_note_service.list_credit_notes(session, page=page, limit=limit)
    return ok([CreditNoteOut.model_validate(r) for r in rows], page_meta(total, page, limit))


@router.post("", status_code=201)
async def create_note(
    body: CreditNoteCreate, _=Depends(require_permission("credit_notes.write")), session: AsyncSession = Depends(get_db)
):
    note = await credit_note_service.create_credit_note(session, body)
    await session.commit()
    return ok(CreditNoteOut.model_validate(note))


@router.get("/{note_id}")
async def get_note(
    note_id: str, _=Depends(require_permission("credit_notes.read")), session: AsyncSession = Depends(get_db)
):
    return ok(CreditNoteOut.model_validate(await credit_note_service.get_credit_note(session, note_id)))


@router.post("/{note_id}/issue")
async def issue_note(
    note_id: str, _=Depends(require_permission("credit_notes.write")), session: AsyncSession = Depends(get_db)
):
    note = await credit_note_service.issue_credit_note(session, note_id)
    await session.commit()
    return ok(CreditNoteOut.model_validate(note))


@router.post("/{note_id}/apply")
async def apply_note(
    note_id: str, body: ApplyIn,
    _=Depends(require_permission("credit_notes.write")), session: AsyncSession = Depends(get_db),
):
    note = await credit_note_service.apply_credit_note(session, note_id, body.invoice_id, body.amount_paise)
    await session.commit()
    return ok(CreditNoteOut.model_validate(note))


@router.post("/{note_id}/void")
async def void_note(
    note_id: str, _=Depends(require_permission("credit_notes.write")), session: AsyncSession = Depends(get_db)
):
    note = await credit_note_service.void_credit_note(session, note_id)
    await session.commit()
    return ok(CreditNoteOut.model_validate(note))
