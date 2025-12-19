# backend/app/schemas/calendar_overrides.py

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class CalendarOverrideCreate(BaseModel):
    target_type: str
    target_id: Optional[int] = None

    date_start: date
    date_end: date

    override_kind: str
    reason: Optional[str] = None
    created_by: Optional[int] = None

    model_config = {"from_attributes": True}


class CalendarOverrideRead(BaseModel):
    id: int

    target_type: str
    target_id: Optional[int] = None

    date_start: date
    date_end: date

    override_kind: str
    reason: Optional[str] = None
    created_by: Optional[int] = None

    created_at: datetime

    model_config = {"from_attributes": True}

