from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RecurringCreate(BaseModel):
    customer_id: str
    name: str
    frequency: str = Field(default="MONTHLY", pattern="^(MONTHLY|QUARTERLY|YEARLY)$")
    interval: int = Field(default=1, ge=1)
    start_date: str
    end_date: str | None = None
    next_run_at: str | None = None
    template: dict = Field(default_factory=dict)


class RecurringUpdate(BaseModel):
    name: str | None = None
    frequency: str | None = None
    interval: int | None = None
    end_date: str | None = None
    next_run_at: str | None = None
    template: dict | None = None


class RecurringOut(ORMModel):
    id: str
    customer_id: str
    name: str
    frequency: str
    interval: int
    start_date: str
    end_date: str | None = None
    next_run_at: str
    status: str
    last_invoice_id: str | None = None
    last_period: str | None = None
    created_at: datetime


class AuditOut(ORMModel):
    id: str
    actor_id: str | None = None
    actor_type: str
    action: str
    entity_type: str
    entity_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    ip: str | None = None
    created_at: datetime
