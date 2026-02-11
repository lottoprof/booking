# backend/app/schemas/client_discounts.py

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel


class ClientDiscountCreate(BaseModel):
    client_id: Optional[int] = None  # NULL = promo for all clients
    discount_percent: float
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ClientDiscountUpdate(BaseModel):
    client_id: Optional[int] = None
    discount_percent: Optional[float] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ClientDiscountRead(BaseModel):
    id: int
    client_id: Optional[int] = None
    discount_percent: float
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    description: Optional[str] = None

    model_config = {"from_attributes": True}
