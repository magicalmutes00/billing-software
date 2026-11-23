"""counter ops phase 2: PIN, SKU/barcode, held orders, shifts, cash movements

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.db.base import Base

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NEW_TABLES = ["held_orders", "pos_shifts", "pos_cash_movements"]
APP_ROLE = "billing_app"


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _tables()

    for table in NEW_TABLES:
        Base.metadata.tables[table].create(bind=bind, checkfirst=True)

    if "users" in existing and "pin_hash" not in _columns("users"):
        op.add_column("users", sa.Column("pin_hash", sa.String(255), nullable=True))

    if "products" in existing:
        cols = _columns("products")
        if "sku" not in cols:
            op.add_column("products", sa.Column("sku", sa.String(80), nullable=True))
        if "barcode" not in cols:
            op.add_column("products", sa.Column("barcode", sa.String(80), nullable=True))
        idx = _indexes("products")
        if "ix_products_sku" not in idx:
            op.create_index("ix_products_sku", "products", ["sku"])
        if "ix_products_barcode" not in idx:
            op.create_index("ix_products_barcode", "products", ["barcode"])

    if bind.dialect.name == "postgresql":
        for table in NEW_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM pg_policies WHERE schemaname = current_schema() "
                    "AND tablename = :t AND policyname = 'tenant_isolation'"
                ),
                {"t": table},
            ).scalar()
            if not exists:
                op.execute(
                    f"CREATE POLICY tenant_isolation ON {table} "
                    f"USING (tenant_id = current_setting('app.tenant_id', true)) "
                    f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
                )
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    bind = op.get_bind()
    existing = _tables()

    if "products" in existing:
        idx = _indexes("products")
        for name in ("ix_products_barcode", "ix_products_sku"):
            if name in idx:
                op.drop_index(name, table_name="products")
        cols = _columns("products")
        for col in ("barcode", "sku"):
            if col in cols:
                op.drop_column("products", col)

    if "users" in existing and "pin_hash" in _columns("users"):
        op.drop_column("users", "pin_hash")

    for table in reversed(NEW_TABLES):
        Base.metadata.tables[table].drop(bind=bind, checkfirst=True)
