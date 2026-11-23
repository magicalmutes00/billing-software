from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class ProductCategory(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "product_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_product_categories_tenant_name"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(20), default="#3538cd")
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_products_tenant_name"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product_categories.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(500))
    base_price_paise: Mapped[int] = mapped_column(default=0)
    tax_rate_pct: Mapped[float] = mapped_column(Float, default=0)
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    barcode: Mapped[str | None] = mapped_column(String(80), index=True)

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", lazy="selectin", cascade="all, delete-orphan"
    )


class ProductVariant(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_product_variants_name"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    price_paise: Mapped[int] = mapped_column(default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped[Product] = relationship(back_populates="variants")


class ModifierGroup(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_modifier_groups_tenant_name"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    min_select: Mapped[int] = mapped_column(default=0)
    max_select: Mapped[int] = mapped_column(default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    modifiers: Mapped[list["Modifier"]] = relationship(
        back_populates="group", lazy="selectin", cascade="all, delete-orphan"
    )


class Modifier(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "modifiers"
    __table_args__ = (UniqueConstraint("group_id", "name", name="uq_modifiers_group_name"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("modifier_groups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    price_paise: Mapped[int] = mapped_column(default=0)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    group: Mapped[ModifierGroup] = relationship(back_populates="modifiers")


class ProductModifierGroup(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "product_modifier_groups"
    __table_args__ = (
        UniqueConstraint("product_id", "group_id", name="uq_product_modifier_groups"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("modifier_groups.id", ondelete="CASCADE"), index=True
    )
