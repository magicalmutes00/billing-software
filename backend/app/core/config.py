from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Billing API"
    environment: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./billing.db"
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
