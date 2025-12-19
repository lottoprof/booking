# backend/app/schemas/client_wallets.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ClientWalletCreate(BaseModel):
    user_id: int
    currency: str = "RUB"

    model_config = {"from_attributes": True}


class ClientWalletUpdate(BaseModel):
    is_blocked: Optional[bool] = None

    model_config = {"from_attributes": True}


class ClientWalletRead(BaseModel):
    id: int
    user_id: int
    currency: str
    balance: float
    is_blocked: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

