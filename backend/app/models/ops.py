from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class RecurringSchedule(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "recurring_schedules"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    frequency: Mapped[str] = mapped_column(String(20), default="MONTHLY")
    interval: Mapped[int] = mapped_column(default=1)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10))
    next_run_at: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    template: Mapped[dict] = mapped_column(JSON, default=dict)
    last_invoice_id: Mapped[str | None] = mapped_column(String(36))
    last_period: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(36))


class WebhookEvent(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "webhook_events"

    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED")
    error: Mapped[str | None] = mapped_column(String(1000))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEvent(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "outbox_events"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))


class Reminder(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "reminders"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    due_at: Mapped[str] = mapped_column(String(10), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="EMAIL")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")


class Attachment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "attachments"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(default=0)
    uploaded_by: Mapped[str | None] = mapped_column(String(36))


class AuditLog(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    actor_type: Mapped[str] = mapped_column(String(20), default="USER")
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
