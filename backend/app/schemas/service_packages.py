# backend/app/schemas/service_packages.py

from typing import Optional
from pydantic import BaseModel


class ServicePackageCreate(BaseModel):
    company_id: int
    name: str
    description: Optional[str] = None
    package_items: str = "[]"
    show_on_pricing: bool = True
    show_on_booking: bool = True

    model_config = {"from_attributes": True}


class ServicePackageUpdate(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None
    description: Optional[str] = None
    package_items: Optional[str] = None
    show_on_pricing: Optional[bool] = None
    show_on_booking: Optional[bool] = None

    model_config = {"from_attributes": True}


class ServicePackageRead(BaseModel):
    id: int
    company_id: int
    name: str
    description: Optional[str] = None
    package_items: str
    is_active: bool
    show_on_pricing: bool
    show_on_booking: bool
    package_price: Optional[float] = None  # computed dynamically

    model_config = {"from_attributes": True}
