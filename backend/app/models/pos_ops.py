from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin, utcnow


class HeldOrder(UUIDPkMixin, TimestampMixin, Base):
    """A parked counter cart, resumable from any register in the shop."""

    __tablename__ = "held_orders"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    cashier_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    cart: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PosShift(UUIDPkMixin, TimestampMixin, Base):
    """A cashier register session: opening float through counted close."""

    __tablename__ = "pos_shifts"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    opening_float_paise: Mapped[int] = mapped_column(default=0)
    closing_count_paise: Mapped[int | None] = mapped_column()
    expected_cash_paise: Mapped[int | None] = mapped_column()
    variance_paise: Mapped[int | None] = mapped_column()
    blind_close: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(500))


class PosCashMovement(UUIDPkMixin, TimestampMixin, Base):
    """Cash in/out of the drawer during a shift (sales, refunds, pay-ins, pay-outs)."""

    __tablename__ = "pos_cash_movements"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    shift_id: Mapped[str] = mapped_column(String(36), ForeignKey("pos_shifts.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    amount_paise: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(String(500))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
