# backend/app/services/booking_payment.py
"""
Booking payment processing service.

Handles payment logic when a booking is confirmed as done (status=done).
Determines whether to use a client package or process as a single service.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.generated import (
    Bookings as DBBooking,
    ClientPackages as DBClientPackage,
    ClientWallets as DBWallet,
    ServicePackages as DBServicePackage,
    WalletTransactions as DBTransaction,
)

logger = logging.getLogger(__name__)


def _get_or_create_wallet(user_id: int, db: Session) -> DBWallet:
    """Get wallet by user_id or create if not exists."""
    wallet = db.query(DBWallet).filter(DBWallet.user_id == user_id).first()
    if wallet:
        return wallet

    wallet = DBWallet(
        user_id=user_id,
        balance=0.0,
        currency="RUB",
        is_blocked=0,
    )
    db.add(wallet)
    db.flush()
    return wallet


def _create_transaction(
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


def _calculate_unit_price(purchase_price: float, package_items: str) -> float:
    """Calculate price per service unit from snapshot purchase_price."""
    items = json.loads(package_items) if package_items else []
    total_qty = sum(item["quantity"] for item in items)
    return purchase_price / total_qty if total_qty > 0 else 0


def _find_active_package(
    db: Session,
    user_id: int,
    package_id: int,
) -> Optional[tuple[DBClientPackage, DBServicePackage]]:
    """
    Find an active client package for the given service_package_id with remaining quantity.

    Returns the package expiring soonest (ORDER BY valid_to ASC).
    Packages with valid_to IS NULL are considered active indefinitely
    and sorted last among active packages.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Get non-closed client packages matching this service package
    client_packages = (
        db.query(DBClientPackage)
        .filter(DBClientPackage.user_id == user_id)
        .filter(DBClientPackage.package_id == package_id)
        .filter(DBClientPackage.is_closed == 0)
        .all()
    )

    candidates = []

    for cp in client_packages:
        # Check valid_to - skip expired
        if cp.valid_to:
            valid_to_date = str(cp.valid_to)[:10]
            if valid_to_date < today:
                continue

        sp = db.get(DBServicePackage, cp.package_id)
        if not sp:
            continue

        # Check remaining quantity: total items qty - total used
        items = json.loads(sp.package_items) if sp.package_items else []
        used = json.loads(cp.used_items) if cp.used_items else {}
        total_qty = sum(item["quantity"] for item in items)
        total_used = sum(used.values())
        remaining = total_qty - total_used

        if remaining > 0:
            sort_key = cp.valid_to if cp.valid_to else "9999-99-99"
            candidates.append((sort_key, cp, sp))

    if not candidates:
        return None

    # Sort by valid_to ASC (expiring soonest first)
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]


def process_booking_payment(
    db: Session,
    booking_id: int,
    created_by: Optional[int] = None,
) -> dict:
    """
    Process payment when booking status is set to done.

    Algorithm:
    1. Get booking (service_package_id, client_id)
    2. Find active client package for service_package_id with remaining quantity
    3. If package found:
       - Calculate unit_price = package_price / total_quantity
       - Increment used_items for all services in package
       - Create withdraw transaction
       - Link booking to package
    4. If no package:
       - Use package base price
       - Create deposit + withdraw transactions
       - booking.client_package_id = NULL

    Args:
        db: Database session
        booking_id: ID of the booking to process
        created_by: Optional user ID who initiated the action

    Returns:
        {
            "source": "package" | "single",
            "amount": float,
            "package_id": int | None,
            "client_package_id": int | None,
            "transactions": [tx_id, ...]
        }
    """
    # Get booking
    booking = db.get(DBBooking, booking_id)
    if not booking:
        raise ValueError(f"Booking {booking_id} not found")

    client_id = booking.client_id
    service_package_id = booking.service_package_id

    if not service_package_id:
        raise ValueError(f"Booking {booking_id} has no service_package_id")

    # Get or create wallet
    wallet = _get_or_create_wallet(client_id, db)

    if wallet.is_blocked:
        logger.warning(f"Wallet for user {client_id} is blocked, skipping payment")
        return {
            "source": "skipped",
            "amount": 0,
            "package_id": None,
            "client_package_id": None,
            "transactions": [],
            "reason": "wallet_blocked",
        }

    # Get service package for name
    service_package = db.get(DBServicePackage, service_package_id)
    if not service_package:
        raise ValueError(f"ServicePackage {service_package_id} not found")

    transactions = []

    # Try to find active client package
    package_result = _find_active_package(db, client_id, service_package_id)

    if package_result:
        # Use package
        client_package, sp = package_result

        # Use snapshot purchase_price; fall back to dynamic calc
        pp = client_package.purchase_price
        if pp is None:
            from .package_pricing import enrich_package_price
            pp = enrich_package_price(sp, db) or 0

        unit_price = _calculate_unit_price(pp, sp.package_items)

        # Increment used_items for all services in the package
        used = json.loads(client_package.used_items) if client_package.used_items else {}
        items = json.loads(sp.package_items) if sp.package_items else []
        for item in items:
            svc_key = str(item["service_id"])
            used[svc_key] = used.get(svc_key, 0) + 1
        client_package.used_items = json.dumps(used)

        # Also update legacy used_quantity for compatibility
        client_package.used_quantity = sum(used.values())

        # Create withdraw transaction
        tx = _create_transaction(
            db=db,
            wallet_id=wallet.id,
            amount=-unit_price,
            tx_type="withdraw",
            booking_id=booking_id,
            description=f"Пакет «{sp.name}»",
            created_by=created_by,
        )
        transactions.append(tx)
        wallet.balance -= unit_price

        # Link booking to package
        booking.client_package_id = client_package.id

        db.flush()

        logger.info(
            f"Booking {booking_id} paid from package {client_package.id}: "
            f"-{unit_price:.2f} RUB"
        )

        return {
            "source": "package",
            "amount": unit_price,
            "package_id": sp.id,
            "client_package_id": client_package.id,
            "transactions": [tx.id for tx in transactions],
        }

    else:
        # No active client package — use package base price with discount
        from .package_pricing import enrich_package_price
        price = enrich_package_price(service_package, db) or 0

        from .discount_resolver import find_best_discount
        discount_pct = find_best_discount(db, client_id, booking_id)
        if discount_pct:
            price = round(price * (1 - discount_pct / 100), 2)

        # Deposit (service rendered)
        tx_deposit = _create_transaction(
            db=db,
            wallet_id=wallet.id,
            amount=price,
            tx_type="deposit",
            booking_id=booking_id,
            description=service_package.name,
            created_by=created_by,
        )
        transactions.append(tx_deposit)
        wallet.balance += price

        # Withdraw (payment)
        tx_withdraw = _create_transaction(
            db=db,
            wallet_id=wallet.id,
            amount=-price,
            tx_type="withdraw",
            booking_id=booking_id,
            description=service_package.name,
            created_by=created_by,
        )
        transactions.append(tx_withdraw)
        wallet.balance -= price

        # No package link
        booking.client_package_id = None

        # Store final price on booking
        booking.final_price = price

        db.flush()

        logger.info(
            f"Booking {booking_id} paid as single: "
            f"+{price:.2f} / -{price:.2f} RUB"
            f"{f' (discount {discount_pct}%)' if discount_pct else ''}"
        )

        return {
            "source": "single",
            "amount": price,
            "discount_percent": discount_pct,
            "package_id": None,
            "client_package_id": None,
            "transactions": [tx.id for tx in transactions],
        }
