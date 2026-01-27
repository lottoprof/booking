"""
Booking completion checker.

Periodically checks for bookings where service time has ended
(date_start + duration_minutes <= now) and emits booking_done events.

Runs as an asyncio task in backend lifespan.
Uses synchronous DB and Redis (via asyncio.to_thread).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from ..database import SessionLocal
from ..models.generated import Bookings
from ..redis_client import redis_client
from .events import emit_event

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # seconds between checks
SENT_KEY_TTL = 900  # 15 minutes — re-send until admin confirms


async def completion_checker_loop() -> None:
    """
    Periodic loop that checks for bookings needing completion confirmation.

    For each booking where date_start + duration_minutes <= now
    and status is still active (pending/confirmed):
    - Emit booking_done event to events:p2p
    - Mark as sent in Redis to avoid duplicates
    """
    logger.info("completion_checker_loop started")

    try:
        while True:
            try:
                await asyncio.to_thread(_check_completed_bookings)
            except asyncio.CancelledError:
                logger.info("completion_checker_loop cancelled")
                raise
            except Exception:
                logger.exception("completion_checker_loop error")

            await asyncio.sleep(CHECK_INTERVAL)
    except asyncio.CancelledError:
        pass


def _check_completed_bookings() -> None:
    """Check for bookings that need completion confirmation (synchronous)."""
    now = datetime.utcnow()

    db = SessionLocal()
    try:
        bookings = (
            db.query(Bookings)
            .filter(Bookings.status.in_(["pending", "confirmed"]))
            .all()
        )

        for booking in bookings:
            try:
                _process_single_booking(booking, now)
            except Exception:
                logger.exception(
                    f"Error processing booking {booking.id} for completion"
                )
    finally:
        db.close()


def _process_single_booking(booking, now: datetime) -> None:
    """Check a single booking and emit event if service time has ended."""
    booking_id = booking.id

    # Check if already sent
    sent_key = f"bkdone:sent:{booking_id}"
    if redis_client.exists(sent_key):
        return

    # Parse date_start
    date_start_str = booking.date_start
    duration_minutes = booking.duration_minutes

    if not date_start_str or not duration_minutes:
        return

    try:
        if isinstance(date_start_str, datetime):
            date_start = date_start_str
        else:
            date_start = datetime.fromisoformat(
                str(date_start_str).replace("Z", "")
            )
    except (ValueError, TypeError):
        return

    # Service end = date_start + duration (without break)
    service_end = date_start + timedelta(minutes=duration_minutes)

    if service_end > now:
        return

    # Emit event and mark as sent
    emit_event("booking_done", {"booking_id": booking_id})
    redis_client.setex(sent_key, SENT_KEY_TTL, "1")

    logger.info(
        f"booking_done emitted for booking={booking_id} "
        f"(service ended at {service_end.strftime('%H:%M')})"
    )
