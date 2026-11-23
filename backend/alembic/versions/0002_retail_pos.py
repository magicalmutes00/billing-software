"""retail catalog and counter POS

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.db.base import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_TABLES = [
    "product_categories",
    "products",
    "product_variants",
    "modifier_groups",
    "modifiers",
    "product_modifier_groups",
]


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _indexes(table: str) -> set[str]:
    bind = op.get_bind()
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _tables()

    for table in NEW_TABLES:
        Base.metadata.tables[table].create(bind=bind, checkfirst=True)

    if "customers" in existing and "is_walkin" not in _columns("customers"):
        op.add_column(
            "customers",
            sa.Column("is_walkin", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "customers" in existing and "ix_customers_is_walkin" not in _indexes("customers"):
        op.create_index("ix_customers_is_walkin", "customers", ["is_walkin"])

    if "invoices" in existing:
        columns = _columns("invoices")
        if "channel" not in columns:
            op.add_column(
                "invoices",
                sa.Column("channel", sa.String(20), nullable=False, server_default="INVOICE"),
            )
        if "pos_meta" not in columns:
            op.add_column("invoices", sa.Column("pos_meta", sa.JSON(), nullable=True))
        if "ix_invoices_channel" not in _indexes("invoices"):
            op.create_index("ix_invoices_channel", "invoices", ["channel"])

    if "invoice_items" in existing:
        columns = _columns("invoice_items")
        if "product_id" not in columns:
            op.add_column("invoice_items", sa.Column("product_id", sa.String(36), nullable=True))
        if "variant_id" not in columns:
            op.add_column("invoice_items", sa.Column("variant_id", sa.String(36), nullable=True))
        if "modifiers" not in columns:
            op.add_column("invoice_items", sa.Column("modifiers", sa.JSON(), nullable=True))

    if bind.dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM pg_policies "
                    "WHERE schemaname = current_schema() "
                    "AND tablename = :table AND policyname = 'tenant_isolation'"
                ),
                {"table": table},
            ).scalar()
            if not exists:
                op.execute(
                    f"CREATE POLICY tenant_isolation ON {table} "
                    f"USING (tenant_id = current_setting('app.tenant_id', true)) "
                    f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
                )


def downgrade() -> None:
    bind = op.get_bind()
    existing = _tables()

    if "invoice_items" in existing:
        columns = _columns("invoice_items")
        for column in ("modifiers", "variant_id", "product_id"):
            if column in columns:
                op.drop_column("invoice_items", column)

    if "invoices" in existing:
        columns = _columns("invoices")
        if "ix_invoices_channel" in _indexes("invoices"):
            op.drop_index("ix_invoices_channel", table_name="invoices")
        for column in ("pos_meta", "channel"):
            if column in columns:
                op.drop_column("invoices", column)

    if "customers" in existing:
        columns = _columns("customers")
        if "ix_customers_is_walkin" in _indexes("customers"):
            op.drop_index("ix_customers_is_walkin", table_name="customers")
        if "is_walkin" in columns:
            op.drop_column("customers", "is_walkin")

    for table in reversed(NEW_TABLES):
        Base.metadata.tables[table].drop(bind=bind, checkfirst=True)
