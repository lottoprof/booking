# backend/app/schemas/company.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CompanyCreate(BaseModel):
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class CompanyRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

