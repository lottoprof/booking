# backend/app/schemas/wallet_transactions.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class WalletTransactionRead(BaseModel):
    id: int
    wallet_id: int
    booking_id: Optional[int] = None
    amount: float
    type: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}

