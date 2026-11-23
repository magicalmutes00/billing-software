from __future__ import annotations

from typing import Protocol


class PaymentProvider(Protocol):
    name: str

    async def create_payment(
        self, *, amount_paise: int, currency: str, order_ref: str, return_url: str
    ) -> dict:
        """Return {provider_ref, checkout_url, status}."""
        ...

    def verify_webhook(self, *, raw_body: bytes, signature: str | None) -> bool:
        ...

    async def refund(self, *, provider_ref: str, amount_paise: int) -> dict:
        ...
