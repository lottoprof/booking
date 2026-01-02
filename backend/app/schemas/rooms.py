from typing import Optional
from pydantic import BaseModel, Field


class RoomCreate(BaseModel):
    location_id: int
    name: str = Field(min_length=1)
    display_order: Optional[int] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class RoomUpdate(BaseModel):
    is_active: Optional[int] = None   # 0 / 1
    name: Optional[str] = Field(default=None, min_length=1)
    display_order: Optional[int] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class RoomRead(BaseModel):
    id: int
    location_id: int
    name: str
    display_order: Optional[int] = None
    notes: Optional[str] = None
    is_active: int

    model_config = {"from_attributes": True}

