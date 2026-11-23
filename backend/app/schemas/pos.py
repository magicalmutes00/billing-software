from __future__ import annotations

from pydantic import BaseModel, Field


class PosItemIn(BaseModel):
    product_id: str
    variant_id: str | None = None
    modifier_ids: list[str] = []
    qty: float = Field(default=1, gt=0)
    discount_paise: int = Field(default=0, ge=0)
    discount_pct: float = Field(default=0, ge=0, le=100)


class PosPaymentIn(BaseModel):
    method: str = "CASH"
    # Exact bill portion covered by this tender (required for split payments).
    amount_paise: int | None = Field(default=None, ge=0)
    # Cash actually handed over (CASH only); change = tendered - amount.
    tendered_paise: int | None = Field(default=None, ge=0)
    reference_no: str | None = None


class PosSaleIn(BaseModel):
    items: list[PosItemIn] = Field(min_length=1)
    discount_paise: int = Field(default=0, ge=0)
    payment: PosPaymentIn | None = None  # legacy single-tender path
    payments: list[PosPaymentIn] | None = None  # mixed-tender split path
    notes: str | None = None
    shift_id: str | None = None


class PosVoidIn(BaseModel):
    reason: str = "Voided at counter"


class PosRefundLineIn(BaseModel):
    item_id: str
    qty: float = Field(gt=0)


class PosRefundIn(BaseModel):
    lines: list[PosRefundLineIn] = []
    amount_paise: int | None = Field(default=None, ge=0)
    reason: str = "Refund at counter"
    method: str | None = None


class PosHoldIn(BaseModel):
    label: str | None = None
    cart: dict


class PosShiftOpenIn(BaseModel):
    opening_float_paise: int = Field(default=0, ge=0)
    blind_close: bool = False
    note: str | None = None


class PosShiftCloseIn(BaseModel):
    closing_count_paise: int = Field(ge=0)
    note: str | None = None


class PosCashMovementIn(BaseModel):
    type: str = Field(pattern="^(CASH_IN|CASH_OUT|NO_SALE)$")
    amount_paise: int = Field(ge=0)
    note: str | None = None


class PinIn(BaseModel):
    pin: str = Field(min_length=4, max_length=12)


class VerifyPinIn(BaseModel):
    pin: str
    permission: str
