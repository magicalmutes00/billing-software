from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ItemIn(BaseModel):
    description: str
    hsn_sac: str | None = None
    qty: float = Field(default=1, gt=0)
    unit_price_paise: int = Field(ge=0)
    discount_paise: int = Field(default=0, ge=0)
    tax_rate_pct: float = Field(default=0, ge=0, le=100)


class ItemOut(ORMModel):
    id: str
    description: str
    hsn_sac: str | None = None
    qty: float
    unit_price_paise: int
    discount_paise: int
    tax_rate_pct: float
    taxable_paise: int
    cgst_paise: int = 0
    sgst_paise: int = 0
    igst_paise: int = 0
    tax_paise: int
    total_paise: int
    position: int
    product_id: str | None = None
    variant_id: str | None = None
    modifiers: list | None = None


class QuoteCreate(BaseModel):
    customer_id: str
    issue_date: date
    valid_until: date | None = None
    items: list[ItemIn] = Field(min_length=1)
    notes: str | None = None
    terms: str | None = None
    currency: str = "INR"


class QuoteUpdate(BaseModel):
    customer_id: str | None = None
    issue_date: date | None = None
    valid_until: date | None = None
    items: list[ItemIn] | None = None
    notes: str | None = None
    terms: str | None = None
    version: int | None = None


class QuoteOut(ORMModel):
    id: str
    customer_id: str
    number: str | None = None
    status: str
    issue_date: date
    valid_until: date | None = None
    subtotal_paise: int
    discount_paise: int
    tax_paise: int
    total_paise: int
    currency: str
    notes: str | None = None
    terms: str | None = None
    converted_invoice_id: str | None = None
    version: int
    created_at: datetime
    items: list[ItemOut] = []


class InvoiceCreate(BaseModel):
    customer_id: str
    issue_date: date
    due_date: date | None = None
    items: list[ItemIn] = Field(min_length=1)
    notes: str | None = None
    terms: str | None = None
    currency: str = "INR"
    tax_mode: str = "EXCLUSIVE"
    quote_id: str | None = None


class InvoiceUpdate(BaseModel):
    customer_id: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    items: list[ItemIn] | None = None
    notes: str | None = None
    terms: str | None = None
    tax_mode: str | None = None
    version: int | None = None


class InvoiceOut(ORMModel):
    id: str
    customer_id: str
    quote_id: str | None = None
    number: str | None = None
    status: str
    issue_date: date
    due_date: date
    subtotal_paise: int
    discount_paise: int
    tax_paise: int
    round_off_paise: int
    total_paise: int
    paid_paise: int
    credited_paise: int
    balance_paise: int
    currency: str
    notes: str | None = None
    terms: str | None = None
    tax_mode: str
    place_of_supply: str | None = None
    channel: str = "INVOICE"
    pos_meta: dict | None = None
    version: int
    created_at: datetime
    items: list[ItemOut] = []
