from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.db.session import get_db
from app.schemas.documents import QuoteCreate, QuoteOut, QuoteUpdate
from app.services import quote_service

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("")
async def list_quotes(
    status: str | None = None, customer_id: str | None = None, page: int = 1, limit: int = 20,
    _=Depends(require_permission("quotes.read")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    rows, total = await quote_service.list_quotes(session, status=status, customer_id=customer_id, page=page, limit=limit)
    return ok([QuoteOut.model_validate(r) for r in rows], page_meta(total, page, limit))


@router.post("", status_code=201)
async def create_quote(
    body: QuoteCreate, _=Depends(require_permission("quotes.write")), session: AsyncSession = Depends(get_db)
):
    quote = await quote_service.create_quote(session, body)
    await session.commit()
    return ok(QuoteOut.model_validate(quote))


@router.get("/{quote_id}")
async def get_quote(
    quote_id: str, _=Depends(require_permission("quotes.read")), session: AsyncSession = Depends(get_db)
):
    return ok(QuoteOut.model_validate(await quote_service.get_quote(session, quote_id)))


@router.patch("/{quote_id}")
async def update_quote(
    quote_id: str, body: QuoteUpdate,
    _=Depends(require_permission("quotes.write")), session: AsyncSession = Depends(get_db),
):
    quote = await quote_service.update_quote(session, quote_id, body)
    await session.commit()
    return ok(QuoteOut.model_validate(quote))


@router.post("/{quote_id}/send")
async def send_quote(
    quote_id: str, _=Depends(require_permission("quotes.send")), session: AsyncSession = Depends(get_db)
):
    quote = await quote_service.send_quote(session, quote_id)
    await session.commit()
    return ok(QuoteOut.model_validate(quote))


@router.post("/{quote_id}/accept")
async def accept_quote(
    quote_id: str, _=Depends(require_permission("quotes.write")), session: AsyncSession = Depends(get_db)
):
    quote = await quote_service.accept_quote(session, quote_id)
    await session.commit()
    return ok(QuoteOut.model_validate(quote))


@router.post("/{quote_id}/reject")
async def reject_quote(
    quote_id: str, _=Depends(require_permission("quotes.write")), session: AsyncSession = Depends(get_db)
):
    quote = await quote_service.reject_quote(session, quote_id)
    await session.commit()
    return ok(QuoteOut.model_validate(quote))


@router.post("/{quote_id}/convert", status_code=201)
async def convert_quote(
    quote_id: str, _=Depends(require_permission("quotes.write")), session: AsyncSession = Depends(get_db)
):
    from app.schemas.documents import InvoiceOut

    invoice = await quote_service.convert_quote(session, quote_id)
    await session.commit()
    return ok(InvoiceOut.model_validate(invoice))
