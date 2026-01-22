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


class BookingUpdate(BaseModel):
    """
    Update schema for bookings.
    
    All fields are optional - only provided fields will be updated.
    """
    # Reschedule
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    
    # Change assignment
    specialist_id: Optional[int] = None
    service_id: Optional[int] = None
    room_id: Optional[int] = None
    
    # Update details
    duration_minutes: Optional[int] = None
    final_price: Optional[float] = None
    
    # Status management
    status: Optional[str] = None
    cancel_reason: Optional[str] = None
    
    # Notes
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


class BookingReadWithDetails(BookingRead):
    """booking with related names for client display."""
    service_name: Optional[str] = None
    specialist_name: Optional[str] = None
    location_name: Optional[str] = None

