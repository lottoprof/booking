# backend/app/schemas/booking_discounts.py

from typing import Optional
from pydantic import BaseModel


class BookingDiscountCreate(BaseModel):
    booking_id: int
    discount_percent: float
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class BookingDiscountRead(BaseModel):
    id: int
    booking_id: int
    discount_percent: float
    description: Optional[str] = None

    model_config = {"from_attributes": True}

