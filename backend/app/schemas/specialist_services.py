# backend/app/schemas/specialist_services.py

from typing import Optional
from pydantic import BaseModel


class SpecialistServiceCreate(BaseModel):
    service_id: int
    specialist_id: int
    is_default: bool = False
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class SpecialistServiceUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class SpecialistServiceRead(BaseModel):
    service_id: int
    specialist_id: int
    is_default: bool
    is_active: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}

