from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class AddressIn(BaseModel):
    type: str = "BILLING"
    line1: str
    line2: str | None = None
    city: str
    state_code: str = Field(min_length=2, max_length=2)
    pincode: str
    is_default: bool = True


class CustomerCreate(BaseModel):
    legal_name: str
    display_name: str
    gstin: str | None = None
    tax_type: str = "UNREGISTERED"
    state_code: str = Field(default="KA", min_length=2, max_length=2)
    email: EmailStr | None = None
    phone: str | None = None
    payment_terms_days: int = Field(default=15, ge=0)
    credit_limit_paise: int | None = None
    notes: str | None = None
    addresses: list[AddressIn] = []


class CustomerUpdate(BaseModel):
    legal_name: str | None = None
    display_name: str | None = None
    gstin: str | None = None
    tax_type: str | None = None
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    email: EmailStr | None = None
    phone: str | None = None
    payment_terms_days: int | None = None
    credit_limit_paise: int | None = None
    status: str | None = None
    notes: str | None = None


class AddressOut(ORMModel):
    id: str
    type: str
    line1: str
    line2: str | None = None
    city: str
    state_code: str
    pincode: str
    is_default: bool


class CustomerOut(ORMModel):
    id: str
    legal_name: str
    display_name: str
    gstin: str | None = None
    tax_type: str
    state_code: str
    email: str | None = None
    phone: str | None = None
    payment_terms_days: int
    credit_limit_paise: int | None = None
    status: str
    notes: str | None = None
    created_at: datetime | None = None
    addresses: list[AddressOut] = []
    outstanding_paise: int = 0
