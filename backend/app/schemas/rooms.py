# backend/app/schemas/rooms.py

from typing import Optional
from pydantic import BaseModel


class RoomCreate(BaseModel):
    location_id: int
    name: str
    display_order: Optional[int] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class RoomUpdate(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None
    display_order: Optional[int] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class RoomRead(BaseModel):
    id: int
    location_id: int
    name: str
    display_order: Optional[int] = None
    notes: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}

