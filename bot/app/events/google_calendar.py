"""
Google Calendar integration event handlers.

Handles: google_calendar_connected, google_calendar_disconnected, google_calendar_auth_failed.
"""

import logging

from . import register_event
from bot.app.utils.api import api
from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)


async def _get_user_tg_id(user_id: int) -> int | None:
    """Get Telegram ID from user_id."""
    user = await api.get_user(user_id)
    if user:
        return user.get("tg_id")
    return None


async def _send_notification(tg_id: int, message_key: str) -> None:
    """Send notification to user via Telegram."""
    from bot.app.main import bot

    if not tg_id:
        return

    lang = user_lang.get(tg_id, DEFAULT_LANG)
    text = t(message_key, lang)

    try:
        await bot.send_message(tg_id, text)
        logger.info(f"Sent Google Calendar notification to tg_id={tg_id}")
    except Exception as e:
        logger.error(f"Failed to send notification to tg_id={tg_id}: {e}")


@register_event("google_calendar_connected")
async def handle_google_calendar_connected(data: dict) -> None:
    """Handle successful Google Calendar connection."""
    user_id = data.get("user_id")
    specialist_id = data.get("specialist_id")

    logger.info(f"Google Calendar connected: specialist_id={specialist_id}, user_id={user_id}")

    if user_id:
        tg_id = await _get_user_tg_id(user_id)
        if tg_id:
            await _send_notification(tg_id, "specialist:gcal:connected")


@register_event("google_calendar_disconnected")
async def handle_google_calendar_disconnected(data: dict) -> None:
    """Handle Google Calendar disconnection."""
    user_id = data.get("user_id")
    specialist_id = data.get("specialist_id")

    logger.info(f"Google Calendar disconnected: specialist_id={specialist_id}, user_id={user_id}")

    # No notification needed - user initiated the disconnect


@register_event("google_calendar_auth_failed")
async def handle_google_calendar_auth_failed(data: dict) -> None:
    """Handle Google Calendar authentication failure (token refresh failed)."""
    user_id = data.get("user_id")
    specialist_id = data.get("specialist_id")

    logger.warning(f"Google Calendar auth failed: specialist_id={specialist_id}, user_id={user_id}")

    if user_id:
        tg_id = await _get_user_tg_id(user_id)
        if tg_id:
            await _send_notification(tg_id, "specialist:gcal:auth_failed")
