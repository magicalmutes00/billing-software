"""hardening: POS indexes + non-owner RLS app role

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Composite indexes for POS daily/range reports and sales lists.
NEW_INDEXES = [
    ("ix_invoices_tenant_channel_issue_date", "invoices", ["tenant_id", "channel", "issue_date"]),
    ("ix_invoices_tenant_channel_created_at", "invoices", ["tenant_id", "channel", "created_at"]),
]

# Tables that carry tenant_id and must be reachable by the non-owner app role.
# (tenants/permissions are global and also granted via ALL TABLES.)
APP_ROLE = "billing_app"
APP_ROLE_PASSWORD = "billing_app"  # dev-only; production should provision a managed role


def _indexes(table: str) -> set[str]:
    bind = op.get_bind()
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _tables()

    for name, table, columns in NEW_INDEXES:
        if table in existing and name not in _indexes(table):
            op.create_index(name, table, columns)

    if bind.dialect.name == "postgresql":
        # Non-owner login role so RLS policies are enforced for the runtime app.
        # The owner role (used by migrations/seed/auth) continues to bypass RLS.
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_ROLE_PASSWORD}' NOBYPASSRLS;
                END IF;
            END
            $$;
            """
        )
        op.execute(f"GRANT CONNECT ON DATABASE {bind.engine.url.database} TO {APP_ROLE}")
        op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
        # Future tables/sequences created by the owner inherit these grants.
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = _tables()

    for name, table, _columns in reversed(NEW_INDEXES):
        if table in existing and name in _indexes(table):
            op.drop_index(name, table_name=table)

    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
        op.execute(f"REVOKE CONNECT ON DATABASE {bind.engine.url.database} FROM {APP_ROLE}")
        op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
