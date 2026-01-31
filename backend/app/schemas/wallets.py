# backend/app/schemas/wallets.py

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Read Schemas
# ──────────────────────────────────────────────────────────────────────────────

class WalletRead(BaseModel):
    """Response for GET /wallets/{user_id}"""
    id: int
    user_id: int
    balance: float
    currency: str
    is_blocked: bool

    model_config = {"from_attributes": True}


class WalletTransactionRead(BaseModel):
    """Transaction item in history list"""
    id: int
    wallet_id: int
    booking_id: Optional[int] = None
    amount: float
    type: str  # deposit, withdraw, payment, refund, correction
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Operation Request Schemas
# ──────────────────────────────────────────────────────────────────────────────

class WalletDeposit(BaseModel):
    """Request body for POST /wallets/{user_id}/deposit"""
    amount: float = Field(..., gt=0, description="Amount to deposit (must be > 0)")
    description: Optional[str] = None
    created_by: Optional[int] = None


class WalletWithdraw(BaseModel):
    """Request body for POST /wallets/{user_id}/withdraw"""
    amount: float = Field(..., gt=0, description="Amount to withdraw (must be > 0)")
    description: Optional[str] = None
    created_by: Optional[int] = None


class WalletPayment(BaseModel):
    """Request body for POST /wallets/{user_id}/payment"""
    amount: float = Field(..., gt=0, description="Payment amount (must be > 0)")
    booking_id: int = Field(..., description="Booking ID (required)")
    description: Optional[str] = None


class WalletRefund(BaseModel):
    """Request body for POST /wallets/{user_id}/refund"""
    amount: float = Field(..., gt=0, description="Refund amount (must be > 0)")
    booking_id: Optional[int] = None
    description: Optional[str] = None
    created_by: Optional[int] = None


class WalletCorrection(BaseModel):
    """Request body for POST /wallets/{user_id}/correction"""
    amount: float = Field(..., description="Correction amount (can be + or -)")
    description: str = Field(..., min_length=3, description="Reason for correction (min 3 chars)")
    created_by: int = Field(..., description="Admin user ID (required)")


class WalletPackagePurchase(BaseModel):
    """Request body for POST /wallets/{user_id}/package-purchase"""
    package_id: int = Field(..., description="Service package ID to purchase")
    valid_to: Optional[str] = Field(None, description="Expiration date (YYYY-MM-DD), optional")
    notes: Optional[str] = Field(None, description="Additional notes")
    created_by: Optional[int] = Field(None, description="Admin user ID who processed the purchase")


class WalletPackagePurchaseResponse(BaseModel):
    """Response for POST /wallets/{user_id}/package-purchase"""
    success: bool
    client_package_id: int
    wallet_transaction_id: int
    new_balance: float
    package_name: str
    package_price: float


class WalletPackageRefund(BaseModel):
    """Request body for POST /wallets/{user_id}/package-refund"""
    client_package_id: int = Field(..., description="Client package ID to refund")
    reason: Optional[str] = Field(None, description="Reason for refund")
    created_by: Optional[int] = Field(None, description="Admin user ID who processed the refund")


class WalletPackageRefundResponse(BaseModel):
    """Response for POST /wallets/{user_id}/package-refund"""
    success: bool
    refund_amount: float
    remaining_services: int
    new_balance: float
    transaction_id: int


# ──────────────────────────────────────────────────────────────────────────────
# Operation Response Schema
# ──────────────────────────────────────────────────────────────────────────────

class WalletOperationResponse(BaseModel):
    """Response after any wallet operation"""
    success: bool
    wallet_id: int
    new_balance: float
    transaction_id: int
    message: Optional[str] = None

