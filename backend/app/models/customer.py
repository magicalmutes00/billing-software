from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class Customer(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "display_name", name="uq_customers_tenant_name"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    tax_type: Mapped[str] = mapped_column(String(20), default="UNREGISTERED")
    state_code: Mapped[str] = mapped_column(String(2), default="KA")
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    payment_terms_days: Mapped[int] = mapped_column(default=15)
    credit_limit_paise: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[str | None] = mapped_column(String(36))
    deleted_at: Mapped[str | None] = mapped_column(String(30))
    is_walkin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    addresses: Mapped[list[CustomerAddress]] = relationship(
        back_populates="customer", lazy="selectin", cascade="all, delete-orphan"
    )


class CustomerAddress(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "customer_addresses"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="BILLING")
    line1: Mapped[str] = mapped_column(String(250))
    line2: Mapped[str | None] = mapped_column(String(250))
    city: Mapped[str] = mapped_column(String(100))
    state_code: Mapped[str] = mapped_column(String(2))
    pincode: Mapped[str] = mapped_column(String(10))
    is_default: Mapped[bool] = mapped_column(default=True)

    customer: Mapped[Customer] = relationship(back_populates="addresses")
