# backend/app/schemas/slots.py
"""
Pydantic schemas for slots API.
"""

from datetime import date
from pydantic import BaseModel, Field


class SlotsDayStatus(BaseModel):
    """Status of a single day in calendar."""
    date: date
    has_slots: bool
    open_slots_count: int = 0
    
    model_config = {"from_attributes": True}


class SlotsCalendarRequest(BaseModel):
    """Request for slots calendar."""
    location_id: int
    start_date: date | None = None  # Defaults to today
    end_date: date | None = None    # Defaults to start_date + horizon_days
    
    model_config = {"from_attributes": True}


class SlotsCalendarResponse(BaseModel):
    """Response with calendar of available days."""
    location_id: int
    start_date: date
    end_date: date
    days: list[SlotsDayStatus]
    
    # Metadata
    horizon_days: int
    min_advance_hours: int
    slot_step_minutes: int = Field(description="Grid step in minutes (15/30/60)")
    
    model_config = {"from_attributes": True}


class SlotInfo(BaseModel):
    """Information about a single slot."""
    slot_index: int
    time: str  # "HH:MM"
    is_available: bool
    
    model_config = {"from_attributes": True}


class SlotsDayRequest(BaseModel):
    """Request for detailed slots of a day."""
    location_id: int
    service_id: int
    date: date
    
    model_config = {"from_attributes": True}


class SlotsDayResponse(BaseModel):
    """Response with detailed slots for a day (Level 2)."""
    location_id: int
    service_id: int
    date: date
    slots: list[SlotInfo]
    
    # For future: specialists and rooms per slot
    # specialists_by_slot: dict[int, list[int]] = {}
    # rooms_by_slot: dict[int, list[int]] = {}
    
    model_config = {"from_attributes": True}


class SlotsGridResponse(BaseModel):
    """Raw grid response (for debugging/admin)."""
    location_id: int
    date: date
    grid: str = Field(description="Grid string: '0' = closed, '1' = open. Length depends on slot_step_minutes: 96 (15min) / 48 (30min) / 24 (60min)")
    cached: bool
    version: int
    slots_per_day: int = Field(description="Number of slots in grid (96/48/24)")
    
    model_config = {"from_attributes": True}
