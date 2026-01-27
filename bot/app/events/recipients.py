"""
Recipient resolution for notification events.

Determines who should receive a notification based on:
- event_type
- notification_settings (DB)
- booking data
- initiated_by (exclude the initiator)
"""

import logging
from typing import Optional
from dataclasses import dataclass

from bot.app.utils.api import api

logger = logging.getLogger(__name__)


@dataclass
class Recipient:
    user_id: int
    tg_id: Optional[int]
    role: str
    push_subscriptions: list[dict]


async def resolve_recipients(
    event_type: str,
    booking: dict,
    initiated_by: Optional[dict] = None,
) -> list[Recipient]:
    """
    Resolve notification recipients for an event.

    Args:
        event_type: e.g. "booking_created", "booking_cancelled"
        booking: full booking dict from API
        initiated_by: {"user_id": int, "role": str} — will be excluded

    Returns:
        List of Recipient objects to notify.
    """
    company_id = booking.get("company_id", 1)

    # Fetch notification settings for this event
    settings = await api.get_notification_settings(
        company_id=company_id,
        event_type=event_type,
    )

    # Build set of roles that should be notified
    enabled_roles = {
        s["recipient_role"]
        for s in settings
        if s.get("enabled")
    }

    if not enabled_roles:
        logger.info(f"No enabled roles for event {event_type}")
        return []

    initiator_user_id = (
        initiated_by.get("user_id") if initiated_by else None
    )

    recipients: list[Recipient] = []

    # Resolve admin recipients
    if "admin" in enabled_roles:
        admins = await api.get_users_by_role("admin")
        for user in admins:
            if user["id"] == initiator_user_id:
                continue
            recipients.append(Recipient(
                user_id=user["id"],
                tg_id=user.get("tg_id"),
                role="admin",
                push_subscriptions=[],
            ))

    # Resolve manager recipients
    if "manager" in enabled_roles:
        managers = await api.get_users_by_role("manager")
        for user in managers:
            if user["id"] == initiator_user_id:
                continue
            recipients.append(Recipient(
                user_id=user["id"],
                tg_id=user.get("tg_id"),
                role="manager",
                push_subscriptions=[],
            ))

    # Resolve specialist recipient (the specialist assigned to this booking)
    if "specialist" in enabled_roles and booking.get("specialist_id"):
        specialist = await api.get_specialist(booking["specialist_id"])
        if specialist:
            spec_user = await api.get_user(specialist["user_id"])
            if spec_user and spec_user.get("is_active"):
                if spec_user["id"] != initiator_user_id:
                    push_subs = await api.get_push_subscriptions_by_user(
                        spec_user["id"]
                    )
                    recipients.append(Recipient(
                        user_id=spec_user["id"],
                        tg_id=spec_user.get("tg_id"),
                        role="specialist",
                        push_subscriptions=push_subs,
                    ))

    # Resolve client recipient
    if "client" in enabled_roles and booking.get("client_id"):
        client = await api.get_user(booking["client_id"])
        if client and client.get("is_active"):
            if client["id"] != initiator_user_id:
                push_subs = await api.get_push_subscriptions_by_user(
                    client["id"]
                )
                recipients.append(Recipient(
                    user_id=client["id"],
                    tg_id=client.get("tg_id"),
                    role="client",
                    push_subscriptions=push_subs,
                ))

    # Deduplicate by user_id
    seen = set()
    unique = []
    for r in recipients:
        if r.user_id not in seen:
            seen.add(r.user_id)
            unique.append(r)

    logger.info(
        f"Resolved {len(unique)} recipients for {event_type}: "
        f"{[(r.role, r.user_id) for r in unique]}"
    )
    return unique


async def get_ad_template_for_event(
    event_type: str,
    recipient_role: str,
    company_id: int,
) -> Optional[dict]:
    """Get ad template attached to notification setting, if any."""
    settings = await api.get_notification_settings(
        company_id=company_id,
        event_type=event_type,
        recipient_role=recipient_role,
    )

    for s in settings:
        template_id = s.get("ad_template_id")
        if template_id:
            template = await api.get_ad_template(template_id)
            if template and template.get("active"):
                return template

    return None
