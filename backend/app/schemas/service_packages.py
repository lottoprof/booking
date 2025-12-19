# backend/app/schemas/service_packages.py

from typing import Optional
from pydantic import BaseModel


class ServicePackageCreate(BaseModel):
    company_id: int
    name: str
    description: Optional[str] = None
    package_items: str = "{}"
    package_price: float

    model_config = {"from_attributes": True}


class ServicePackageUpdate(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None
    description: Optional[str] = None
    package_items: Optional[str] = None
    package_price: Optional[float] = None

    model_config = {"from_attributes": True}


class ServicePackageRead(BaseModel):
    id: int
    company_id: int
    name: str
    description: Optional[str] = None
    package_items: str
    package_price: float
    is_active: bool

    model_config = {"from_attributes": True}

