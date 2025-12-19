# backend/app/schemas/client_packages.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ClientPackageCreate(BaseModel):
    user_id: int
    package_id: int

    model_config = {"from_attributes": True}


class ClientPackageRead(BaseModel):
    id: int
    user_id: int
    package_id: int
    used_quantity: int
    purchased_at: datetime
    valid_to: Optional[datetime] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}

