from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class Payment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_payments_tenant_number"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    number: Mapped[str | None] = mapped_column(String(40))
    amount_paise: Mapped[int] = mapped_column(default=0)
    allocated_paise: Mapped[int] = mapped_column(default=0)
    method: Mapped[str] = mapped_column(String(20), default="MANUAL")
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="CAPTURED", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference_no: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[str | None] = mapped_column(String(36))
    receipt_key: Mapped[str | None] = mapped_column(String(255))

    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", lazy="selectin", cascade="all, delete-orphan"
    )


class PaymentAllocation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    payment_id: Mapped[str] = mapped_column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(default=0)

    payment: Mapped[Payment] = relationship(back_populates="allocations")


class CreditNote(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "credit_notes"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_credit_notes_tenant_number"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"))
    number: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    subtotal_paise: Mapped[int] = mapped_column(default=0)
    tax_paise: Mapped[int] = mapped_column(default=0)
    total_paise: Mapped[int] = mapped_column(default=0)
    applied_paise: Mapped[int] = mapped_column(default=0)
    tax_mode: Mapped[str] = mapped_column(String(10), default="EXCLUSIVE")
    cgst_paise: Mapped[int] = mapped_column(default=0)
    sgst_paise: Mapped[int] = mapped_column(default=0)
    igst_paise: Mapped[int] = mapped_column(default=0)
    refund_mode: Mapped[str] = mapped_column(String(20), default="ADJUSTMENT")

    allocations: Mapped[list["CreditNoteAllocation"]] = relationship(
        back_populates="credit_note", lazy="selectin", cascade="all, delete-orphan"
    )


class CreditNoteAllocation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "credit_note_allocations"
    __table_args__ = (UniqueConstraint("credit_note_id", "invoice_id", name="uq_credit_note_invoice"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    credit_note_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credit_notes.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(default=0)

    credit_note: Mapped[CreditNote] = relationship(back_populates="allocations")
