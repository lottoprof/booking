from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    event_type: str

    actor_user_id: Optional[int] = None
    target_user_id: Optional[int] = None

    payload: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

