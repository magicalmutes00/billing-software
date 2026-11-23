from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class TenantOut(ORMModel):
    id: str
    name: str
    slug: str
    legal_name: str | None = None
    gstin: str | None = None
    state_code: str
    address_line1: str | None = None
    city: str | None = None
    pincode: str | None = None
    currency: str
    settings: dict = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    gstin: str | None = None
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    address_line1: str | None = None
    city: str | None = None
    pincode: str | None = None
    currency: str | None = None
    settings: dict | None = None


class SettingsUpdate(BaseModel):
    settings: dict


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    roles: list[str] = []


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    status: str
    roles: list[str] = []
