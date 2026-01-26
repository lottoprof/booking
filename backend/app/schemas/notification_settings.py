from typing import Optional
from pydantic import BaseModel


class NotificationSettingsCreate(BaseModel):
    event_type: str
    recipient_role: str
    channel: str = "all"
    enabled: int = 1
    ad_template_id: Optional[int] = None
    company_id: int

    model_config = {"from_attributes": True}


class NotificationSettingsUpdate(BaseModel):
    enabled: Optional[int] = None
    ad_template_id: Optional[int] = None
    channel: Optional[str] = None

    model_config = {"from_attributes": True}


class NotificationSettingsRead(BaseModel):
    id: int
    event_type: str
    recipient_role: str
    channel: str
    enabled: int
    ad_template_id: Optional[int] = None
    company_id: int

    model_config = {"from_attributes": True}
