# backend/app/routers/wallets.py
"""
Wallet Domain API — финансовые операции с кошельками клиентов.

Все операции создают записи в wallet_transactions.
CRUD для client_wallets и wallet_transactions запрещён (read-only через другие роуты).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import (
    ClientWallets as DBWallet,
    WalletTransactions as DBTransaction,
    Users as DBUser,
    Bookings as DBBooking,
)
from ..schemas.wallets import (
    WalletRead,
    WalletTransactionRead,
    WalletDeposit,
    WalletWithdraw,
    WalletPayment,
    WalletRefund,
    WalletCorrection,
    WalletOperationResponse,
)

router = APIRouter(prefix="/wallets", tags=["wallets"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_or_create_wallet(user_id: int, db: Session) -> DBWallet:
    """
    Get wallet by user_id or create if not exists.
    Raises 404 if user doesn't exist.
    """
    wallet = db.query(DBWallet).filter(DBWallet.user_id == user_id).first()
    
    if wallet:
        return wallet
    
    # Check user exists
    user = db.get(DBUser, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )
    
    # Create wallet with zero balance
    wallet = DBWallet(
        user_id=user_id,
        balance=0.0,
        currency="RUB",
        is_blocked=0,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    
    return wallet


def check_wallet_not_blocked(wallet: DBWallet):
    """Raise 403 if wallet is blocked."""
    if wallet.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wallet is blocked"
        )


def check_sufficient_balance(wallet: DBWallet, amount: float):
    """Raise 400 if insufficient balance."""
    if wallet.balance < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance: {wallet.balance:.2f} < {amount:.2f}"
        )


def create_transaction(
    db: Session,
    wallet_id: int,
    amount: float,
    tx_type: str,
    booking_id: Optional[int] = None,
    description: Optional[str] = None,
    created_by: Optional[int] = None,
) -> DBTransaction:
    """Create a wallet transaction record."""
    tx = DBTransaction(
        wallet_id=wallet_id,
        amount=amount,
        type=tx_type,
        booking_id=booking_id,
        description=description,
        created_by=created_by,
    )
    db.add(tx)
    return tx


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=WalletRead)
def get_wallet(user_id: int, db: Session = Depends(get_db)):
    """
    Get user wallet.
    Creates wallet with balance=0 if not exists.
    """
    wallet = get_or_create_wallet(user_id, db)
    return wallet


@router.get("/{user_id}/transactions", response_model=list[WalletTransactionRead])
def get_transactions(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Get wallet transaction history.
    Ordered by created_at DESC (newest first).
    """
    wallet = get_or_create_wallet(user_id, db)
    
    transactions = (
        db.query(DBTransaction)
        .filter(DBTransaction.wallet_id == wallet.id)
        .order_by(DBTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    return transactions


@router.post("/{user_id}/deposit", response_model=WalletOperationResponse)
def deposit(
    user_id: int,
    data: WalletDeposit,
    db: Session = Depends(get_db),
):
    """
    Deposit funds to wallet.
    Increases balance by amount.
    """
    wallet = get_or_create_wallet(user_id, db)
    check_wallet_not_blocked(wallet)
    
    # Create transaction (positive amount)
    tx = create_transaction(
        db=db,
        wallet_id=wallet.id,
        amount=data.amount,  # positive
        tx_type="deposit",
        description=data.description,
        created_by=data.created_by,
    )
    
    # Update balance
    wallet.balance += data.amount
    
    db.commit()
    db.refresh(wallet)
    db.refresh(tx)
    
    return WalletOperationResponse(
        success=True,
        wallet_id=wallet.id,
        new_balance=wallet.balance,
        transaction_id=tx.id,
        message=f"Deposited {data.amount:.2f} {wallet.currency}",
    )


@router.post("/{user_id}/withdraw", response_model=WalletOperationResponse)
def withdraw(
    user_id: int,
    data: WalletWithdraw,
    db: Session = Depends(get_db),
):
    """
    Withdraw funds from wallet.
    Decreases balance by amount.
    Requires sufficient balance.
    """
    wallet = get_or_create_wallet(user_id, db)
    check_wallet_not_blocked(wallet)
    check_sufficient_balance(wallet, data.amount)
    
    # Create transaction (negative amount)
    tx = create_transaction(
        db=db,
        wallet_id=wallet.id,
        amount=-data.amount,  # negative
        tx_type="withdraw",
        description=data.description,
        created_by=data.created_by,
    )
    
    # Update balance
    wallet.balance -= data.amount
    
    db.commit()
    db.refresh(wallet)
    db.refresh(tx)
    
    return WalletOperationResponse(
        success=True,
        wallet_id=wallet.id,
        new_balance=wallet.balance,
        transaction_id=tx.id,
        message=f"Withdrawn {data.amount:.2f} {wallet.currency}",
    )


@router.post("/{user_id}/payment", response_model=WalletOperationResponse)
def payment(
    user_id: int,
    data: WalletPayment,
    db: Session = Depends(get_db),
):
    """
    Pay for a booking from wallet.
    Requires booking_id and sufficient balance.
    """
    wallet = get_or_create_wallet(user_id, db)
    check_wallet_not_blocked(wallet)
    
    # Check booking exists
    booking = db.get(DBBooking, data.booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {data.booking_id} not found"
        )
    
    check_sufficient_balance(wallet, data.amount)
    
    # Create transaction (negative amount)
    tx = create_transaction(
        db=db,
        wallet_id=wallet.id,
        amount=-data.amount,  # negative
        tx_type="payment",
        booking_id=data.booking_id,
        description=data.description,
    )
    
    # Update balance
    wallet.balance -= data.amount
    
    db.commit()
    db.refresh(wallet)
    db.refresh(tx)
    
    return WalletOperationResponse(
        success=True,
        wallet_id=wallet.id,
        new_balance=wallet.balance,
        transaction_id=tx.id,
        message=f"Payment {data.amount:.2f} for booking #{data.booking_id}",
    )


@router.post("/{user_id}/refund", response_model=WalletOperationResponse)
def refund(
    user_id: int,
    data: WalletRefund,
    db: Session = Depends(get_db),
):
    """
    Refund funds to wallet.
    Increases balance by amount.
    """
    wallet = get_or_create_wallet(user_id, db)
    check_wallet_not_blocked(wallet)
    
    # Check booking exists if provided
    if data.booking_id:
        booking = db.get(DBBooking, data.booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking {data.booking_id} not found"
            )
    
    # Create transaction (positive amount)
    tx = create_transaction(
        db=db,
        wallet_id=wallet.id,
        amount=data.amount,  # positive
        tx_type="refund",
        booking_id=data.booking_id,
        description=data.description,
        created_by=data.created_by,
    )
    
    # Update balance
    wallet.balance += data.amount
    
    db.commit()
    db.refresh(wallet)
    db.refresh(tx)
    
    msg = f"Refunded {data.amount:.2f} {wallet.currency}"
    if data.booking_id:
        msg += f" for booking #{data.booking_id}"
    
    return WalletOperationResponse(
        success=True,
        wallet_id=wallet.id,
        new_balance=wallet.balance,
        transaction_id=tx.id,
        message=msg,
    )


@router.post("/{user_id}/correction", response_model=WalletOperationResponse)
def correction(
    user_id: int,
    data: WalletCorrection,
    db: Session = Depends(get_db),
):
    """
    Admin correction of wallet balance.
    Amount can be positive (add) or negative (subtract).
    Requires description and created_by.
    """
    wallet = get_or_create_wallet(user_id, db)
    check_wallet_not_blocked(wallet)
    
    # For negative corrections, check balance
    if data.amount < 0 and wallet.balance < abs(data.amount):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Correction would result in negative balance: {wallet.balance:.2f} + ({data.amount:.2f})"
        )
    
    # Create transaction (amount as-is, can be + or -)
    tx = create_transaction(
        db=db,
        wallet_id=wallet.id,
        amount=data.amount,
        tx_type="correction",
        description=data.description,
        created_by=data.created_by,
    )
    
    # Update balance
    wallet.balance += data.amount
    
    db.commit()
    db.refresh(wallet)
    db.refresh(tx)
    
    sign = "+" if data.amount >= 0 else ""
    return WalletOperationResponse(
        success=True,
        wallet_id=wallet.id,
        new_balance=wallet.balance,
        transaction_id=tx.id,
        message=f"Correction {sign}{data.amount:.2f}: {data.description}",
    )

