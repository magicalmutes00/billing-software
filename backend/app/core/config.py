from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Billing API"
    environment: str = "dev"
    # Managed hosts usually inject DATABASE_URL with the legacy `postgres://`
    # scheme. SQLAlchemy 2.x needs an explicit driver, and asyncpg does not
    # accept libpq-only query parameters, so normalise both here.
    database_url: str = Field(
        default="sqlite+aiosqlite:///./billing.db",
        validation_alias=AliasChoices("MANAGED_DATABASE_URL", "DATABASE_URL", "PRIMARY_DATABASE_URL"),
    )
    # Runtime app connection. When set (PostgreSQL), use a NON-owner role so RLS
    # policies are enforced. database_url stays the owner role for migrations/seed.
    # Defaults to database_url (SQLite dev/test, where RLS is a no-op).
    app_database_url: str | None = None
    jwt_secret: str = "dev-only-change-me-32-bytes-minimum"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    portal_token_hours: int = 24
    payment_provider: str = "stub"
    webhook_secret: str = "dev-webhook-secret"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "./storage"

    @model_validator(mode="after")
    def normalize_database_url(self) -> "Settings":
        url = self.database_url.strip()
        parts = urlsplit(url)
        if parts.scheme in {"postgres", "postgresql", "postgresql+asyncpg"}:
            query = [
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if key not in {"sslmode", "channel_binding"}
            ]
            url = urlunsplit((
                "postgresql+asyncpg",
                parts.netloc,
                parts.path,
                urlencode(query),
                parts.fragment,
            ))
        self.database_url = url
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
