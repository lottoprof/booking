# backend/app/schemas/locations.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class LocationCreate(BaseModel):
    company_id: int
    name: str

    country: Optional[str] = None
    region: Optional[str] = None
    city: str
    street: Optional[str] = None
    house: Optional[str] = None
    building: Optional[str] = None
    office: Optional[str] = None
    postal_code: Optional[str] = None

    work_schedule: str = "{}"
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class LocationUpdate(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None
    work_schedule: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class LocationRead(BaseModel):
    id: int
    company_id: int
    name: str

    country: Optional[str] = None
    region: Optional[str] = None
    city: str
    street: Optional[str] = None
    house: Optional[str] = None
    building: Optional[str] = None
    office: Optional[str] = None
    postal_code: Optional[str] = None

    is_active: bool
    work_schedule: str
    notes: Optional[str] = None

    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

