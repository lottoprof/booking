"""
bot/app/services/google_calendar_sync.py

Google Calendar sync service for bookings.

Handles synchronization of booking events to specialist's Google Calendar.
"""

import logging
from typing import Literal

from bot.app.utils.api import api

logger = logging.getLogger(__name__)

SyncAction = Literal["create", "update", "delete"]


async def sync_booking_to_google(
    booking_id: int,
    action: SyncAction,
) -> bool:
    """
    Sync a booking to Google Calendar.

    This function is called from booking event handlers to sync
    booking changes to the specialist's Google Calendar.

    Args:
        booking_id: ID of the booking to sync
        action: Sync action - 'create', 'update', or 'delete'

    Returns:
        True if sync was successful or not needed, False on error
    """
    logger.info(f"Syncing booking {booking_id} to Google Calendar: action={action}")

    try:
        result = await api.sync_booking_to_calendar(booking_id, action)

        if result is None:
            logger.warning(f"Sync API call failed for booking {booking_id}")
            return False

        if result.get("synced"):
            logger.info(
                f"Booking {booking_id} synced to Google Calendar: "
                f"event_id={result.get('event_id')}, action={result.get('action')}"
            )
            return True
        else:
            reason = result.get("reason", "Unknown")
            logger.info(f"Booking {booking_id} not synced: {reason}")
            # Not an error if no integration exists
            return True

    except Exception as e:
        logger.exception(f"Error syncing booking {booking_id} to Google Calendar: {e}")
        return False
