from typing import Optional
from pydantic import BaseModel


class AdTemplateCreate(BaseModel):
    name: str
    content_tg: str
    content_html: Optional[str] = None
    active: int = 1
    valid_until: Optional[str] = None
    company_id: int

    model_config = {"from_attributes": True}


class AdTemplateUpdate(BaseModel):
    name: Optional[str] = None
    content_tg: Optional[str] = None
    content_html: Optional[str] = None
    active: Optional[int] = None
    valid_until: Optional[str] = None

    model_config = {"from_attributes": True}


class AdTemplateRead(BaseModel):
    id: int
    name: str
    content_tg: str
    content_html: Optional[str] = None
    active: int
    valid_until: Optional[str] = None
    company_id: int

    model_config = {"from_attributes": True}
