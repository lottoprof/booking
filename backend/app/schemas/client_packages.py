# backend/app/schemas/client_packages.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ClientPackageCreate(BaseModel):
    user_id: int
    package_id: int
    valid_to: Optional[datetime] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ClientPackageRead(BaseModel):
    id: int
    user_id: int
    package_id: int
    used_quantity: int
    used_items: str  # JSON string {"service_id": quantity_used, ...}
    is_closed: bool
    purchased_at: datetime
    valid_to: Optional[datetime] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ClientPackageWithRemaining(ClientPackageRead):
    """Client package with remaining service counts."""
    package_name: str
    package_price: float
    remaining_items: dict  # {service_id: remaining_count}
    total_quantity: int
    total_remaining: int

