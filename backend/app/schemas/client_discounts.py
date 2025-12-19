# backend/app/schemas/client_discounts.py

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel


class ClientDiscountCreate(BaseModel):
    client_id: int
    discount_percent: float
    valid_to: Optional[date] = None
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ClientDiscountUpdate(BaseModel):
    discount_percent: Optional[float] = None
    valid_to: Optional[date] = None
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ClientDiscountRead(BaseModel):
    id: int
    client_id: int
    discount_percent: float
    valid_to: Optional[date] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

