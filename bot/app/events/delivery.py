"""
Notification delivery module.

Routes notifications to the appropriate channel:
- tg_id → Telegram (bot.send_message)
- push_subscription → Web Push (pywebpush)
"""

import json
import logging
import os
from typing import Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.app.utils.api import api
from bot.app.i18n.loader import t, DEFAULT_LANG
from .recipients import Recipient, resolve_recipients, get_ad_template_for_event
from .formatters import format_event

logger = logging.getLogger(__name__)

# VAPID keys for Web Push (optional)
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "")


async def deliver_booking_event(event_type: str, data: dict) -> None:
    """
    Main entry point for delivering a booking notification event.

    1. Fetch booking data
    2. Resolve recipients (exclude initiator)
    3. Format message per recipient role
    4. Deliver via Telegram / Web Push
    """
    booking_id = data.get("booking_id")
    initiated_by = data.get("initiated_by")

    booking = await api.get_booking(booking_id)
    if not booking:
        logger.error(f"Booking not found: {booking_id}")
        return

    recipients = await resolve_recipients(event_type, booking, initiated_by)
    if not recipients:
        logger.info(f"No recipients for {event_type} booking={booking_id}")
        return

    for recipient in recipients:
        try:
            await _deliver_to_recipient(
                event_type=event_type,
                booking=booking,
                recipient=recipient,
                data=data,
            )
        except Exception:
            logger.exception(
                f"Failed to deliver {event_type} to user={recipient.user_id}"
            )


async def _deliver_to_recipient(
    event_type: str,
    booking: dict,
    recipient: Recipient,
    data: dict,
) -> None:
    """Deliver notification to a single recipient via all available channels."""
    company_id = booking.get("company_id", 1)

    # Check for ad template
    ad_template = await get_ad_template_for_event(
        event_type, recipient.role, company_id
    )
    ad_text = ad_template.get("content_tg") if ad_template else None

    # Format message
    text = await format_event(
        event_type=event_type,
        booking=booking,
        recipient_role=recipient.role,
        ad_text=ad_text,
        old_datetime=data.get("old_datetime"),
        new_datetime=data.get("new_datetime"),
    )

    # Build keyboard for admin notifications
    keyboard = _build_keyboard(event_type, booking, recipient.role)

    # Deliver via Telegram
    if recipient.tg_id:
        await _send_telegram(recipient.tg_id, text, keyboard)

    # Deliver via Web Push (if no tg_id or has push subscriptions)
    if recipient.push_subscriptions and not recipient.tg_id:
        plain_text = text.replace("<b>", "").replace("</b>", "")
        for sub in recipient.push_subscriptions:
            await _send_web_push(sub, plain_text)


def _build_keyboard(
    event_type: str,
    booking: dict,
    recipient_role: str,
    lang: str = DEFAULT_LANG,
) -> Optional[InlineKeyboardMarkup]:
    """Build inline keyboard for the notification."""
    booking_id = booking.get("id")

    if event_type == "booking_done" and recipient_role == "admin":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common:no", lang),
                    callback_data=f"bkn:done_no:{booking_id}",
                ),
                InlineKeyboardButton(
                    text=t("common:yes", lang),
                    callback_data=f"bkn:done_yes:{booking_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("common:hide", lang),
                    callback_data=f"bkn:hide:{booking_id}",
                ),
            ],
        ])

    if recipient_role == "admin":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common:edit", lang),
                    callback_data=f"bkn:edit:{booking_id}",
                ),
                InlineKeyboardButton(
                    text=t("common:hide", lang),
                    callback_data=f"bkn:hide:{booking_id}",
                ),
            ]
        ])

    # No keyboard for client / specialist notifications
    return None


async def _send_telegram(
    tg_id: int,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Send a Telegram message via bot instance."""
    from bot.app.main import bot

    try:
        await bot.send_message(
            chat_id=tg_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        logger.info(f"Telegram notification sent to tg_id={tg_id}")
    except Exception as e:
        logger.warning(f"Failed to send Telegram to tg_id={tg_id}: {e}")


async def _send_web_push(subscription: dict, text: str) -> None:
    """Send a Web Push notification."""
    if not VAPID_PRIVATE_KEY:
        logger.debug("VAPID_PRIVATE_KEY not set, skipping Web Push")
        return

    try:
        from pywebpush import webpush

        sub_info = {
            "endpoint": subscription.get("endpoint"),
            "keys": {
                "auth": subscription.get("auth", ""),
                "p256dh": subscription.get("p256dh", ""),
            },
        }

        webpush(
            subscription_info=sub_info,
            data=json.dumps({"title": "Booking", "body": text[:200]}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{VAPID_EMAIL}"},
        )
        logger.info(
            f"Web Push sent to endpoint={subscription.get('endpoint', '')[:50]}..."
        )
    except Exception as e:
        logger.warning(f"Web Push failed: {e}")
