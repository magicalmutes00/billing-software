from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str = Field(default="#3538cd", max_length=20)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=20)
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryOut(ORMModel):
    id: str
    name: str
    color: str
    sort_order: int
    is_active: bool
    created_at: datetime


class VariantIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price_paise: int = Field(ge=0)
    is_default: bool = False
    sort_order: int = 0
    is_active: bool = True


class VariantOut(ORMModel):
    id: str
    name: str
    price_paise: int
    is_default: bool
    sort_order: int
    is_active: bool


class ModifierIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price_paise: int = Field(default=0, ge=0)
    sort_order: int = 0
    is_active: bool = True


class ModifierOut(ORMModel):
    id: str
    name: str
    price_paise: int
    sort_order: int
    is_active: bool


class ModifierGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    min_select: int = Field(default=0, ge=0)
    max_select: int = Field(default=1, ge=0)
    is_required: bool = False
    sort_order: int = 0
    is_active: bool = True
    modifiers: list[ModifierIn] = []


class ModifierGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    min_select: int | None = Field(default=None, ge=0)
    max_select: int | None = Field(default=None, ge=0)
    is_required: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    modifiers: list[ModifierIn] | None = None


class ModifierGroupOut(ORMModel):
    id: str
    name: str
    min_select: int
    max_select: int
    is_required: bool
    sort_order: int
    is_active: bool
    modifiers: list[ModifierOut] = []


class ProductIn(BaseModel):
    category_id: str
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    base_price_paise: int = Field(default=0, ge=0)
    tax_rate_pct: float = Field(default=0, ge=0, le=100)
    hsn_sac: str | None = None
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    sort_order: int = 0
    is_active: bool = True
    variants: list[VariantIn] = []
    modifier_group_ids: list[str] = []


class ProductUpdate(BaseModel):
    category_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    base_price_paise: int | None = Field(default=None, ge=0)
    tax_rate_pct: float | None = Field(default=None, ge=0, le=100)
    hsn_sac: str | None = None
    sku: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    sort_order: int | None = None
    is_active: bool | None = None
    variants: list[VariantIn] | None = None
    modifier_group_ids: list[str] | None = None


class ProductOut(BaseModel):
    id: str
    category_id: str
    name: str
    description: str | None = None
    base_price_paise: int
    tax_rate_pct: float
    hsn_sac: str | None = None
    sku: str | None = None
    barcode: str | None = None
    sort_order: int
    is_active: bool
    created_at: datetime
    variants: list[VariantOut] = []
    modifier_group_ids: list[str] = []


class MenuProduct(BaseModel):
    id: str
    category_id: str
    name: str
    description: str | None = None
    base_price_paise: int
    tax_rate_pct: float
    hsn_sac: str | None = None
    sku: str | None = None
    barcode: str | None = None
    sort_order: int
    variants: list[VariantOut] = []
    modifier_groups: list[ModifierGroupOut] = []


class MenuCategory(BaseModel):
    id: str
    name: str
    color: str
    sort_order: int
    products: list[MenuProduct] = []
