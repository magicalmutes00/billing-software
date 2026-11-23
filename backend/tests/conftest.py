from __future__ import annotations

import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "test_billing.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["JWT_SECRET"] = "test-only-secret-that-is-long-enough-for-hs256"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"

import pytest_asyncio  # noqa: E402

from app.core.context import tenant_id_var  # noqa: E402
from app.db.session import SessionLocal, admin_engine, engine, init_db  # noqa: E402
from app.services.auth_service import create_tenant_with_owner  # noqa: E402


@pytest_asyncio.fixture
async def db():
    if DB_PATH.exists():
        DB_PATH.unlink()
    await init_db()
    async with SessionLocal() as session:
        tenant = await create_tenant_with_owner(
            session,
            name="Test Studio",
            slug="test",
            email="owner@test.example.com",
            password="Password123!",
            full_name="Test Owner",
            state_code="KA",
            gstin="29ABCDE1234F1Z5",
        )
        # Fixture setup and teardown run in different asyncio contexts, so the
        # ContextVar token cannot be reset here. Each test starts from a fresh DB.
        tenant_id_var.set(tenant.id)
        yield session, tenant
    # Dispose BOTH engines (app + admin) so neither holds a lock on the SQLite
    # file before deletion (Windows WinError 32 otherwise).
    await engine.dispose()
    await admin_engine.dispose()
    if DB_PATH.exists():
        DB_PATH.unlink(missing_ok=True)
