from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class DocumentSequence(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "document_sequences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "series", "year", name="uq_document_sequence"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    series: Mapped[str] = mapped_column(String(20), default="MAIN")
    year: Mapped[str] = mapped_column(String(4))
    next_number: Mapped[int] = mapped_column(default=1)


class Quote(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_quotes_tenant_number"),)

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    number: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    issue_date: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    subtotal_paise: Mapped[int] = mapped_column(default=0)
    discount_paise: Mapped[int] = mapped_column(default=0)
    tax_paise: Mapped[int] = mapped_column(default=0)
    total_paise: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    notes: Mapped[str | None] = mapped_column(String(2000))
    terms: Mapped[str | None] = mapped_column(String(2000))
    converted_invoice_id: Mapped[str | None] = mapped_column(String(36))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1)

    items: Mapped[list[QuoteItem]] = relationship(
        back_populates="quote", lazy="selectin", cascade="all, delete-orphan"
    )


class QuoteItem(UUIDPkMixin, Base):
    __tablename__ = "quote_items"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    quote_id: Mapped[str] = mapped_column(String(36), ForeignKey("quotes.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    qty: Mapped[float] = mapped_column(Float, default=1)
    unit_price_paise: Mapped[int] = mapped_column(default=0)
    discount_paise: Mapped[int] = mapped_column(default=0)
    tax_rate_pct: Mapped[float] = mapped_column(Float, default=0)
    taxable_paise: Mapped[int] = mapped_column(default=0)
    cgst_paise: Mapped[int] = mapped_column(default=0)
    sgst_paise: Mapped[int] = mapped_column(default=0)
    igst_paise: Mapped[int] = mapped_column(default=0)
    tax_paise: Mapped[int] = mapped_column(default=0)
    total_paise: Mapped[int] = mapped_column(default=0)
    position: Mapped[int] = mapped_column(default=0)

    quote: Mapped[Quote] = relationship(back_populates="items")


class Invoice(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_invoices_tenant_number"),
        Index("ix_invoices_tenant_channel_issue_date", "tenant_id", "channel", "issue_date"),
        Index("ix_invoices_tenant_channel_created_at", "tenant_id", "channel", "created_at"),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    quote_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("quotes.id"))
    number: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    subtotal_paise: Mapped[int] = mapped_column(default=0)
    discount_paise: Mapped[int] = mapped_column(default=0)
    tax_paise: Mapped[int] = mapped_column(default=0)
    round_off_paise: Mapped[int] = mapped_column(default=0)
    total_paise: Mapped[int] = mapped_column(default=0)
    paid_paise: Mapped[int] = mapped_column(default=0)
    credited_paise: Mapped[int] = mapped_column(default=0)
    balance_paise: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    notes: Mapped[str | None] = mapped_column(String(2000))
    terms: Mapped[str | None] = mapped_column(String(2000))
    tax_mode: Mapped[str] = mapped_column(String(10), default="EXCLUSIVE")
    place_of_supply: Mapped[str | None] = mapped_column(String(2))
    channel: Mapped[str] = mapped_column(String(20), default="INVOICE", index=True)
    pos_meta: Mapped[dict | None] = mapped_column(JSON)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_key: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(30))

    items: Mapped[list[InvoiceItem]] = relationship(
        back_populates="invoice", lazy="selectin", cascade="all, delete-orphan"
    )


class InvoiceItem(UUIDPkMixin, Base):
    __tablename__ = "invoice_items"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    qty: Mapped[float] = mapped_column(Float, default=1)
    unit_price_paise: Mapped[int] = mapped_column(default=0)
    discount_paise: Mapped[int] = mapped_column(default=0)
    tax_rate_pct: Mapped[float] = mapped_column(Float, default=0)
    taxable_paise: Mapped[int] = mapped_column(default=0)
    cgst_paise: Mapped[int] = mapped_column(default=0)
    sgst_paise: Mapped[int] = mapped_column(default=0)
    igst_paise: Mapped[int] = mapped_column(default=0)
    tax_paise: Mapped[int] = mapped_column(default=0)
    total_paise: Mapped[int] = mapped_column(default=0)
    position: Mapped[int] = mapped_column(default=0)
    product_id: Mapped[str | None] = mapped_column(String(36))
    variant_id: Mapped[str | None] = mapped_column(String(36))
    modifiers: Mapped[list | None] = mapped_column(JSON)

    invoice: Mapped[Invoice] = relationship(back_populates="items")
