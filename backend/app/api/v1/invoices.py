from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.db.session import get_db
from app.schemas.documents import InvoiceCreate, InvoiceOut, InvoiceUpdate
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("")
async def list_invoices(
    status: str | None = None, customer_id: str | None = None, channel: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    search: str | None = None, page: int = 1, limit: int = 20,
    _=Depends(require_permission("invoices.read")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    rows, total = await invoice_service.list_invoices(
        session, status=status, customer_id=customer_id, channel=channel,
        date_from=date_from, date_to=date_to, search=search, page=page, limit=limit,
    )
    return ok([InvoiceOut.model_validate(r) for r in rows], page_meta(total, page, limit))


@router.post("", status_code=201)
async def create_invoice(
    body: InvoiceCreate, _=Depends(require_permission("invoices.write")), session: AsyncSession = Depends(get_db)
):
    invoice = await invoice_service.create_invoice(session, body)
    await session.commit()
    return ok(InvoiceOut.model_validate(invoice))


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str, _=Depends(require_permission("invoices.read")), session: AsyncSession = Depends(get_db)
):
    return ok(InvoiceOut.model_validate(await invoice_service.get_invoice(session, invoice_id)))


@router.patch("/{invoice_id}")
async def update_invoice(
    invoice_id: str, body: InvoiceUpdate,
    _=Depends(require_permission("invoices.write")), session: AsyncSession = Depends(get_db),
):
    invoice = await invoice_service.update_invoice(session, invoice_id, body)
    await session.commit()
    return ok(InvoiceOut.model_validate(invoice))


@router.post("/{invoice_id}/send")
async def send_invoice(
    invoice_id: str, _=Depends(require_permission("invoices.send")), session: AsyncSession = Depends(get_db)
):
    invoice = await invoice_service.send_invoice(session, invoice_id)
    await session.commit()
    return ok(InvoiceOut.model_validate(invoice))


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: str, _=Depends(require_permission("invoices.cancel")), session: AsyncSession = Depends(get_db)
):
    invoice = await invoice_service.cancel_invoice(session, invoice_id)
    await session.commit()
    return ok(InvoiceOut.model_validate(invoice))


@router.get("/{invoice_id}/pdf", response_class=HTMLResponse)
async def invoice_pdf(
    invoice_id: str, _=Depends(require_permission("invoices.read")), session: AsyncSession = Depends(get_db)
):
    """Printable A4 HTML invoice; use the browser's Print → Save as PDF."""
    return HTMLResponse(await invoice_service.invoice_html(session, invoice_id))
