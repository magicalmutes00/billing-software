from pydantic import BaseModel, EmailStr

from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    shop: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class PortalTokenIn(BaseModel):
    token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PortalTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    customer_id: str


class MeOut(ORMModel):
    id: str
    email: str
    full_name: str
    tenant_id: str
    tenant_name: str | None = None
    roles: list[str] = []
    permissions: list[str] = []
