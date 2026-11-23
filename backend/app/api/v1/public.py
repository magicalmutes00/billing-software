from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.context import tenant_id_var
from app.core.errors import not_found
from app.core.security import decode_token
from app.db.session import SessionLocal, set_tenant_context
from app.services import pos_service

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/receipt/{token}", response_class=HTMLResponse)
async def public_receipt(token: str):
    """Tokenized, expiring receipt link shareable over WhatsApp/SMS (no login)."""
    try:
        claims = decode_token(token, kind="receipt")
    except ValueError:
        raise not_found("Receipt link is invalid or expired")
    invoice_id = claims["sub"]
    tid = claims["tid"]
    tenant_token = tenant_id_var.set(tid)
    try:
        async with SessionLocal() as session:
            await set_tenant_context(session, tid)
            html = await pos_service.receipt_html(session, invoice_id)
        return HTMLResponse(html)
    finally:
        tenant_id_var.reset(tenant_token)
