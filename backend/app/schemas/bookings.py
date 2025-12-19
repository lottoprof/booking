# backend/app/schemas/bookings.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class BookingCreate(BaseModel):
    company_id: int
    location_id: int
    service_id: int
    client_id: int
    specialist_id: int
    room_id: Optional[int] = None

    date_start: datetime
    date_end: datetime

    duration_minutes: int
    break_minutes: int = 0

    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class BookingRead(BaseModel):
    id: int

    company_id: int
    location_id: int
    service_id: int
    client_id: int
    specialist_id: int
    room_id: Optional[int] = None

    date_start: datetime
    date_end: datetime

    duration_minutes: int
    break_minutes: int

    status: str
    final_price: Optional[float] = None
    notes: Optional[str] = None
    cancel_reason: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

