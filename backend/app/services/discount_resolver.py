# backend/app/services/discount_resolver.py
"""
Discount resolution for bookings without a package.

Rule: discounts do NOT stack.  Apply the single maximum:
  max(individual, promo, single-booking)

- individual: client_discounts WHERE user_id = X
- promo:      client_discounts WHERE user_id IS NULL
- single:     booking_discounts WHERE booking_id = X
"""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from ..models.generated import (
    ClientDiscounts as DBClientDiscount,
    BookingDiscounts as DBBookingDiscount,
)


def find_best_discount(
    db: Session,
    user_id: int,
    booking_id: int,
) -> Optional[float]:
    """
    Find the best applicable discount percent for a booking.

    Returns:
        discount_percent (0-100) or None if no discount applies.
    """
    today = date.today().isoformat()

    # Client discounts: individual (user_id = X) OR promo (user_id IS NULL)
    client_discounts = (
        db.query(DBClientDiscount)
        .filter(
            (DBClientDiscount.user_id == user_id) | (DBClientDiscount.user_id.is_(None))
        )
        .all()
    )

    best = 0.0

    for cd in client_discounts:
        # Check valid_from
        if cd.valid_from and cd.valid_from > today:
            continue
        # Check valid_to
        if cd.valid_to and cd.valid_to < today:
            continue
        if cd.discount_percent > best:
            best = cd.discount_percent

    # Booking-specific discount (admin override)
    booking_discounts = (
        db.query(DBBookingDiscount)
        .filter(DBBookingDiscount.booking_id == booking_id)
        .all()
    )

    for bd in booking_discounts:
        if bd.discount_percent > best:
            best = bd.discount_percent

    return best if best > 0 else None
