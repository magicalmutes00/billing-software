from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import ok
from app.core.context import tenant_id_var
from app.core.errors import bad_request
from app.core.security import utcnow
from app.db.session import get_admin_db
from app.models import Payment
from app.models.ops import WebhookEvent
from app.providers.payments import get_provider
from app.services.payment_service import capture_payment

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/payments/{provider}")
async def payment_webhook(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_admin_db),
    x_webhook_signature: str | None = Header(default=None),
):
    gateway = get_provider(provider)
    raw = await request.body()
    if not gateway.verify_webhook(raw_body=raw, signature=x_webhook_signature):
        raise bad_request("Invalid webhook signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise bad_request("Invalid JSON payload") from exc
    event_id = str(payload.get("id") or payload.get("event_id") or payload.get("provider_ref", "unknown"))
    existing = await session.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    if existing:
        return ok({"duplicate": True, "event_id": event_id})

    provider_ref = payload.get("provider_ref") or payload.get("payment_ref")
    payment = None
    if provider_ref:
        payment = await session.scalar(select(Payment).where(Payment.provider_ref == str(provider_ref)))
    event = WebhookEvent(
        tenant_id=payment.tenant_id if payment else None,
        provider=provider,
        event_id=event_id,
        payload=payload,
        status="PROCESSED",
        processed_at=utcnow(),
    )
    session.add(event)
    status = str(payload.get("status", "")).upper()
    if payment and status in {"CAPTURED", "PAID", "SUCCESS"}:
        token = tenant_id_var.set(payment.tenant_id)
        try:
            await capture_payment(session, payment.id, str(provider_ref))
        finally:
            tenant_id_var.reset(token)
    elif payment and status in {"FAILED", "REFUNDED"}:
        payment.status = status
    await session.commit()
    return ok({"duplicate": False, "event_id": event_id})
