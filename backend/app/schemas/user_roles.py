# backend/app/schemas/user_roles.py

from typing import Optional
from pydantic import BaseModel


class UserRoleCreate(BaseModel):
    user_id: int
    role_id: int
    location_id: Optional[int] = None

    model_config = {"from_attributes": True}


class UserRoleRead(BaseModel):
    id: int
    user_id: int
    role_id: int
    location_id: Optional[int] = None

    model_config = {"from_attributes": True}

