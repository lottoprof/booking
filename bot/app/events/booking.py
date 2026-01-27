"""
Booking event handlers.

Handles: booking_created, booking_cancelled, booking_rescheduled, booking_done, booking_reminder.
"""

import logging

from . import register_event

logger = logging.getLogger(__name__)


@register_event("booking_created")
async def handle_booking_created(data: dict) -> None:
    """Handle new booking creation — notify all relevant parties."""
    from .delivery import deliver_booking_event

    booking_id = data.get("booking_id")
    if not booking_id:
        logger.error("booking_created event without booking_id")
        return

    await deliver_booking_event("booking_created", data)


@register_event("booking_cancelled")
async def handle_booking_cancelled(data: dict) -> None:
    """Handle booking cancellation — notify affected parties."""
    from .delivery import deliver_booking_event

    booking_id = data.get("booking_id")
    if not booking_id:
        logger.error("booking_cancelled event without booking_id")
        return

    await deliver_booking_event("booking_cancelled", data)


@register_event("booking_rescheduled")
async def handle_booking_rescheduled(data: dict) -> None:
    """Handle booking reschedule — notify affected parties."""
    from .delivery import deliver_booking_event

    booking_id = data.get("booking_id")
    if not booking_id:
        logger.error("booking_rescheduled event without booking_id")
        return

    await deliver_booking_event("booking_rescheduled", data)


@register_event("booking_done")
async def handle_booking_done(data: dict) -> None:
    """Handle booking completion — ask admin/manager to confirm service delivery."""
    from .delivery import deliver_booking_event

    booking_id = data.get("booking_id")
    if not booking_id:
        logger.error("booking_done event without booking_id")
        return

    await deliver_booking_event("booking_done", data)


@register_event("booking_reminder")
async def handle_booking_reminder(data: dict) -> None:
    """Handle booking reminder — notify client before appointment."""
    from .delivery import deliver_booking_event

    booking_id = data.get("booking_id")
    if not booking_id:
        logger.error("booking_reminder event without booking_id")
        return

    await deliver_booking_event("booking_reminder", data)
