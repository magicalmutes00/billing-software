"""PostgreSQL-only hardening tests (B3 numbering concurrency, B4 RLS isolation).

Run against a real PostgreSQL database, e.g. the Docker Compose stack:
  $env:PG_TEST_URL = "postgresql+asyncpg://billing:billing@localhost:5432/billing"
  python -m pytest tests/test_postgres.py -q

These tests SKIP when PG_TEST_URL is unset (the default SQLite suite is unaffected).
"""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.context import tenant_id_var
from app.db.base import Base
from app.models import Invoice
from app.services.auth_service import create_tenant_with_owner
from app.services.numbering import next_number

PG_URL = os.environ.get("PG_TEST_URL")

pytestmark = pytest.mark.skipif(not PG_URL, reason="PG_TEST_URL not set; PostgreSQL-only test")


@pytest.mark.asyncio
async def test_numbering_concurrent_first_sales_unique():
    engine = create_async_engine(PG_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        tenant = await create_tenant_with_owner(
            session, name="PG Race", slug="pg-race", email="race@pg.example.com",
            password="Password123!", state_code="KA",
        )
        await session.commit()
    tid = tenant.id

    async def one_number() -> str:
        async with Session() as session:
            tenant_id_var.set(tid)
            number = await next_number(session, tid, "POS_SALE")
            await session.commit()
            return number

    try:
        numbers = await asyncio.gather(*(one_number() for _ in range(12)))
        assert len(set(numbers)) == 12, f"duplicate BILL numbers under concurrency: {numbers}"
    finally:
        async with Session() as session:
            await session.execute(text("DELETE FROM document_sequences WHERE tenant_id = :t"), {"t": tid})
            await session.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": tid})
            await session.execute(text("DELETE FROM roles WHERE tenant_id = :t"), {"t": tid})
            await session.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tid})
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_reads_for_app_role():
    owner_engine = create_async_engine(PG_URL, future=True)
    async with owner_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure the non-owner app role exists with RLS-subject grants.
        await conn.execute(text(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='billing_app') "
            "THEN CREATE ROLE billing_app LOGIN PASSWORD 'billing_app' NOBYPASSRLS; END IF; END $$;"
        ))
        await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO billing_app"))
        await conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO billing_app"))
        for table in ("invoices", "customers"):
            await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
            await conn.execute(text(
                f"CREATE POLICY tenant_isolation ON {table} "
                f"USING (tenant_id = current_setting('app.tenant_id', true)) "
                f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
            ))
    OwnerSession = async_sessionmaker(owner_engine, expire_on_commit=False)
    async with OwnerSession() as session:
        a = await create_tenant_with_owner(session, name="RLS A", slug="rls-a", email="a@rls.example.com", password="Password123!", state_code="KA")
        b = await create_tenant_with_owner(session, name="RLS B", slug="rls-b", email="b@rls.example.com", password="Password123!", state_code="KA")
        await session.commit()
    aid, bid = a.id, b.id

    app_url = PG_URL.replace("billing:billing", "billing_app:billing_app")
    app_engine = create_async_engine(app_url, future=True)
    AppSession = async_sessionmaker(app_engine, expire_on_commit=False)
    try:
        async with AppSession() as session:
            await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": aid})
            tenant_id_var.set(aid)
            # Tenant A context must not see tenant B rows even without an explicit filter.
            rows = (await session.scalars(select(Invoice))).all()
            assert all(row.tenant_id == aid for row in rows)
    finally:
        async with OwnerSession() as session:
            for t in (aid, bid):
                await session.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": t})
                await session.execute(text("DELETE FROM roles WHERE tenant_id = :t"), {"t": t})
                await session.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": t})
            await session.commit()
        await app_engine.dispose()
        await owner_engine.dispose()
