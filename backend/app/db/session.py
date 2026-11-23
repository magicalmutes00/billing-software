from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.context import actor_id_var, tenant_id_var
from app.core.security import decode_token
from app.db.base import Base

settings = get_settings()

# Runtime app connection: a NON-owner PostgreSQL role (billing_app) so RLS applies.
# Falls back to database_url for SQLite dev/test, where RLS is a no-op.
engine = create_async_engine(settings.app_database_url or settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

# Privileged owner connection for migrations, seed, and cross-tenant auth resolution
# (login/refresh/portal-token/webhooks). The owner bypasses RLS by design.
admin_engine = create_async_engine(settings.database_url, echo=False, future=True)
AdminSessionLocal = async_sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


def _install_sqlite_pragma(target_engine) -> None:
    @event.listens_for(target_engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        if settings.database_url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


_install_sqlite_pragma(engine)
_install_sqlite_pragma(admin_engine)


async def set_tenant_context(session: AsyncSession, tenant_id: str | None) -> None:
    """Set the DB-level tenant context (Postgres RLS). No-op for SQLite dev DB."""
    if settings.database_url.startswith("sqlite"):
        return
    await session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id})


async def current_db_tenant(session: AsyncSession) -> str | None:
    """Read the current DB-level tenant context, if any."""
    if settings.database_url.startswith("sqlite"):
        return None
    return await session.scalar(text("SELECT current_setting('app.tenant_id', true)"))


def claims_from_request(request: Request) -> dict | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        return decode_token(header.split(" ", 1)[1].strip())
    except ValueError:
        return None


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    claims = claims_from_request(request)
    tenant_token = tenant_id_var.set(claims["tid"] if claims else None)
    actor_token = actor_id_var.set(
        (claims.get("cid") if claims.get("kind") == "portal" else claims.get("sub")) if claims else None
    )
    async with SessionLocal() as session:
        await set_tenant_context(session, tenant_id_var.get())
        try:
            yield session
        finally:
            tenant_id_var.reset(tenant_token)
            actor_id_var.reset(actor_token)


async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
    """Privileged owner session for cross-tenant auth resolution and webhooks.

    Use only where a tenant context cannot yet be established (login, refresh,
    portal token issuance, provider webhooks). The owner role bypasses RLS.
    """
    async with AdminSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables for local/dev environments. Production uses Alembic migrations."""
    if settings.environment == "production":
        return
    async with admin_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
