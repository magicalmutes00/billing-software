from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import bad_request
from app.providers.payments.stub import StubProvider

settings = get_settings()
_PROVIDERS = {"stub": StubProvider()}


def get_provider(name: str | None = None):
    provider_name = (name or settings.payment_provider).lower()
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        raise bad_request(f"Unknown payment provider: {provider_name}")
    return provider
