# backend/app/schemas/services.py

from typing import Optional
from pydantic import BaseModel


class ServiceCreate(BaseModel):
    company_id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    duration_min: int
    break_min: int = 0
    price: float
    price_5: Optional[float] = None
    price_10: Optional[float] = None
    color_code: Optional[str] = None

    model_config = {"from_attributes": True}


class ServiceUpdate(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    duration_min: Optional[int] = None
    break_min: Optional[int] = None
    price: Optional[float] = None
    price_5: Optional[float] = None
    price_10: Optional[float] = None
    color_code: Optional[str] = None

    model_config = {"from_attributes": True}


class ServiceRead(BaseModel):
    id: int
    company_id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    duration_min: int
    break_min: int
    price: float
    price_5: Optional[float] = None
    price_10: Optional[float] = None
    color_code: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class ServiceVariant(BaseModel):
    label: str
    qty: int = 1
    price: float
    old_price: Optional[float] = None
    per_session: Optional[float] = None


class PricingCard(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    category: Optional[str] = None
    icon: str = "✦"
    duration_min: int
    variants: list[ServiceVariant] = []

