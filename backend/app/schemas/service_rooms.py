# backend/app/schemas/service_rooms.py

from typing import Optional
from pydantic import BaseModel


class ServiceRoomCreate(BaseModel):
    room_id: int
    service_id: int
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ServiceRoomUpdate(BaseModel):
    is_active: Optional[bool] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ServiceRoomRead(BaseModel):
    id: int
    room_id: int
    service_id: int
    is_active: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}

