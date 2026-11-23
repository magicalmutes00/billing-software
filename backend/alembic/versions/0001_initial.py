"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-21
"""

from alembic import op

from app import models  # noqa: F401
from app.db.base import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    # PostgreSQL: enforce tenant isolation at the database layer via RLS.
    if bind.dialect.name == "postgresql":
        tables = [
            "users", "roles", "refresh_tokens", "customers", "customer_addresses",
            "document_sequences", "quotes", "quote_items", "invoices", "invoice_items",
            "payments", "payment_allocations", "credit_notes", "credit_note_allocations",
            "recurring_schedules", "webhook_events", "outbox_events", "reminders",
            "attachments", "audit_logs",
        ]
        for table in tables:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} "
                f"USING (tenant_id = current_setting('app.tenant_id', true)) "
                f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
            )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
