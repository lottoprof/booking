# backend/app/schemas/push_subscriptions.py

from datetime import datetime
from pydantic import BaseModel


class PushSubscriptionCreate(BaseModel):
    user_id: int
    endpoint: str
    auth: str
    p256dh: str

    model_config = {"from_attributes": True}


class PushSubscriptionRead(BaseModel):
    id: int
    user_id: int
    endpoint: str
    auth: str
    p256dh: str
    created_at: datetime

    model_config = {"from_attributes": True}

