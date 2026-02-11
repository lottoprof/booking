# backend/app/schemas/slots.py
"""
Pydantic schemas for slots API.
"""

from datetime import date, datetime
from pydantic import BaseModel, Field


class SlotsDayStatus(BaseModel):
    """Status of a single day in calendar."""
    date: date
    has_slots: bool
    open_slots_count: int = 0

    model_config = {"from_attributes": True}


class SlotsCalendarResponse(BaseModel):
    """Response with calendar of available days."""
    location_id: int
    start_date: date
    end_date: date
    days: list[SlotsDayStatus]
    horizon_days: int
    min_advance_hours: int
    slot_step_minutes: int = Field(description="Grid step in minutes (15/30/60)")

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Level 2: Day slots
# ──────────────────────────────────────────────────────────────────────────────

class SpecialistInfo(BaseModel):
    """Specialist available in a time slot."""
    id: int
    name: str


class AvailableTimeSlot(BaseModel):
    """Available time slot with specialists."""
    time: str  # "HH:MM"
    specialists: list[SpecialistInfo]


class SlotsDayResponse(BaseModel):
    """Response with detailed slots for a day (Level 2)."""
    location_id: int
    service_id: int | None = None
    service_package_id: int | None = None
    date: str  # ISO date string
    service_duration_min: int
    slots_needed: int
    available_times: list[AvailableTimeSlot]

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Debug
# ──────────────────────────────────────────────────────────────────────────────

class SlotDebugEntry(BaseModel):
    """Single slot in debug output."""
    time: str  # "HH:MM"
    expires_at: datetime


class SlotsGridResponse(BaseModel):
    """Debug response showing sorted set contents."""
    location_id: int
    date: date
    slots: list[SlotDebugEntry]
    total_slots: int
    cached: bool

    model_config = {"from_attributes": True}
