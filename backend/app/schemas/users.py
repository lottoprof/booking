# backend/app/schemas/users.py

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel


class UserCreate(BaseModel):
    company_id: int
    first_name: str
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tg_id: Optional[int] = None
    tg_username: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tg_id: Optional[int] = None
    tg_username: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class UserRead(BaseModel):
    id: int
    company_id: int
    first_name: str
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    tg_id: Optional[int] = None
    tg_username: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------

class UserStatsRead(BaseModel):
    """Booking statistics for a user."""
    user_id: int
    total_bookings: int
    active_bookings: int
    completed_bookings: int
    cancelled_bookings: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------
# Role change
# ---------------------------------------------------------------------

class RoleChangeRequest(BaseModel):
    """Request to change user role."""
    role: Literal["client", "specialist", "manager"]

    model_config = {"from_attributes": True}


class RoleChangeResponse(BaseModel):
    """Response after role change."""
    user_id: int
    old_role: str
    new_role: str

    model_config = {"from_attributes": True}

