"""
Booking reminder checker.

Periodically checks for upcoming bookings and emits booking_reminder events
to notify clients before their appointment.

Each location has its own remind_before_minutes setting.
0 = reminders disabled for that location.

Runs as an asyncio task in backend lifespan.
Uses synchronous DB and Redis (via asyncio.to_thread).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from ..database import SessionLocal
from ..models.generated import Bookings, Locations
from ..redis_client import redis_client
from .events import emit_event

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # seconds between checks
SENT_KEY_TTL = 86400  # 24 hours — reminder is sent once per booking


async def reminder_checker_loop() -> None:
    """
    Periodic loop that checks for bookings needing a reminder.

    For each booking where date_start - remind_before_minutes <= now < date_start
    and status is pending/confirmed:
    - Emit booking_reminder event to events:p2p
    - Mark as sent in Redis to avoid duplicates
    """
    logger.info("reminder_checker_loop started")

    try:
        while True:
            try:
                await asyncio.to_thread(_check_upcoming_bookings)
            except asyncio.CancelledError:
                logger.info("reminder_checker_loop cancelled")
                raise
            except Exception:
                logger.exception("reminder_checker_loop error")

            await asyncio.sleep(CHECK_INTERVAL)
    except asyncio.CancelledError:
        pass


def _check_upcoming_bookings() -> None:
    """Check for bookings that need a reminder (synchronous)."""
    now = datetime.utcnow()

    db = SessionLocal()
    try:
        bookings = (
            db.query(Bookings, Locations.remind_before_minutes)
            .join(Locations, Bookings.location_id == Locations.id)
            .filter(
                Bookings.status.in_(["pending", "confirmed"]),
                Locations.remind_before_minutes > 0,
            )
            .all()
        )

        for booking, remind_before in bookings:
            try:
                _process_single_booking(booking, remind_before, now)
            except Exception:
                logger.exception(
                    f"Error processing booking {booking.id} for reminder"
                )
    finally:
        db.close()


def _process_single_booking(
    booking, remind_before: int, now: datetime
) -> None:
    """Check a single booking and emit reminder if within the reminder window."""
    booking_id = booking.id

    # Check if already sent
    sent_key = f"bkremind:sent:{booking_id}"
    if redis_client.exists(sent_key):
        return

    # Parse date_start
    date_start_str = booking.date_start
    if not date_start_str:
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

    # Reminder window: date_start - remind_before <= now < date_start
    reminder_time = date_start - timedelta(minutes=remind_before)

    if now < reminder_time or now >= date_start:
        return

    # Emit event and mark as sent
    emit_event("booking_reminder", {"booking_id": booking_id})
    redis_client.setex(sent_key, SENT_KEY_TTL, "1")

    logger.info(
        f"booking_reminder emitted for booking={booking_id} "
        f"(starts at {date_start.strftime('%H:%M')}, "
        f"reminded {remind_before} min before)"
    )
