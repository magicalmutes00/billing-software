from __future__ import annotations

import hashlib
import hmac
import uuid

from app.core.config import get_settings

settings = get_settings()


class StubProvider:
    name = "stub"

    async def create_payment(self, *, amount_paise: int, currency: str, order_ref: str, return_url: str) -> dict:
        ref = f"stub_{uuid.uuid4().hex[:16]}"
        return {
            "provider_ref": ref,
            "checkout_url": f"/portal/checkout/stub?payment_ref={ref}&order={order_ref}",
            "status": "PENDING",
        }

    def verify_webhook(self, *, raw_body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        expected = hmac.new(settings.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def refund(self, *, provider_ref: str, amount_paise: int) -> dict:
        return {"provider_ref": f"refund_{provider_ref}", "status": "REFUNDED"}
