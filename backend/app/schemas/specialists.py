# backend/app/schemas/specialists.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SpecialistCreate(BaseModel):
    user_id: int
    display_name: Optional[str] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    work_schedule: str = "{}"

    model_config = {"from_attributes": True}


class SpecialistUpdate(BaseModel):
    is_active: Optional[bool] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    work_schedule: Optional[str] = None

    model_config = {"from_attributes": True}


class SpecialistRead(BaseModel):
    id: int
    user_id: int
    display_name: Optional[str] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    work_schedule: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

