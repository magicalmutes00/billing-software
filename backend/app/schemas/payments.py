from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.documents import ItemIn


class AllocationIn(BaseModel):
    invoice_id: str
    amount_paise: int = Field(gt=0)


class PaymentCreate(BaseModel):
    customer_id: str
    amount_paise: int = Field(gt=0)
    method: str = "MANUAL"
    provider: str | None = None
    provider_ref: str | None = None
    reference_no: str | None = None
    notes: str | None = None
    paid_at: datetime | None = None
    allocations: list[AllocationIn] = []


class AllocationOut(ORMModel):
    id: str
    invoice_id: str
    amount_paise: int


class PaymentOut(ORMModel):
    id: str
    customer_id: str
    number: str | None = None
    amount_paise: int
    allocated_paise: int
    method: str
    provider: str | None = None
    provider_ref: str | None = None
    status: str
    paid_at: datetime | None = None
    reference_no: str | None = None
    notes: str | None = None
    created_at: datetime
    allocations: list[AllocationOut] = []


class AllocateIn(BaseModel):
    allocations: list[AllocationIn] = Field(min_length=1)


class RefundIn(BaseModel):
    amount_paise: int | None = Field(default=None, gt=0)
    reason: str = "Refund"


class CreditNoteCreate(BaseModel):
    customer_id: str
    invoice_id: str | None = None
    reason: str
    items: list[ItemIn] = Field(min_length=1)
    tax_mode: str = "EXCLUSIVE"
    refund_mode: str = "ADJUSTMENT"


class CreditNoteOut(ORMModel):
    id: str
    customer_id: str
    invoice_id: str | None = None
    number: str | None = None
    reason: str
    status: str
    subtotal_paise: int
    tax_paise: int
    total_paise: int
    applied_paise: int
    tax_mode: str
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    refund_mode: str
    created_at: datetime
