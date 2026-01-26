"""
Message formatting for notification events.

Per event_type + per recipient_role formatting.
HTML parse_mode for Telegram.
"""

import logging
from datetime import datetime
from typing import Optional

from bot.app.utils.api import api

logger = logging.getLogger(__name__)


def _format_dt(iso_str: str) -> str:
    """Format ISO datetime to human-readable: '28.01.2026 14:00'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", ""))
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_str


async def _enrich_booking(booking: dict) -> dict:
    """Fetch related entities for display."""
    enriched = dict(booking)

    if booking.get("client_id"):
        client = await api.get_user(booking["client_id"])
        if client:
            name = f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()
            enriched["client_name"] = name or "—"
            enriched["client_phone"] = client.get("phone")

    if booking.get("location_id"):
        location = await api.get_location(booking["location_id"])
        if location:
            enriched["location_name"] = location.get("name", "")

    if booking.get("service_id"):
        service = await api.get_service(booking["service_id"])
        if service:
            enriched["service_name"] = service.get("name", "")
            enriched["service_duration"] = service.get("duration_min", 0)

    if booking.get("specialist_id"):
        specialist = await api.get_specialist(booking["specialist_id"])
        if specialist:
            enriched["specialist_name"] = (
                specialist.get("display_name") or f"#{specialist['id']}"
            )

    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# booking_created
# ─────────────────────────────────────────────────────────────────────────────

async def format_booking_created(
    booking: dict,
    recipient_role: str,
    ad_text: Optional[str] = None,
) -> str:
    """Format booking_created notification."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    if recipient_role == "client":
        lines = [
            f"<b>Запись подтверждена #{booking_id}</b>",
            "",
        ]
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        if b.get("service_name"):
            dur = b.get("service_duration", "")
            lines.append(f"💇 {b['service_name']}" + (f" · {dur} мин" if dur else ""))
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        if b.get("specialist_name"):
            lines.append(f"👨‍💼 {b['specialist_name']}")
    elif recipient_role == "specialist":
        lines = [
            f"📅 <b>Новая запись #{booking_id}</b>",
            "",
        ]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("client_phone"):
            lines.append(f"📞 {b['client_phone']}")
        if b.get("service_name"):
            dur = b.get("service_duration", "")
            lines.append(f"💇 {b['service_name']}" + (f" · {dur} мин" if dur else ""))
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
    else:
        # admin / default
        lines = [
            f"📅 <b>Новая запись #{booking_id}</b>",
            "",
        ]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("client_phone"):
            lines.append(f"📞 {b['client_phone']}")
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        if b.get("service_name"):
            dur = b.get("service_duration", "")
            lines.append(f"💇 {b['service_name']}" + (f" · {dur} мин" if dur else ""))
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        if b.get("specialist_name"):
            lines.append(f"👨‍💼 {b['specialist_name']}")

    if ad_text:
        lines.extend(["", "---", ad_text])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# booking_cancelled
# ─────────────────────────────────────────────────────────────────────────────

async def format_booking_cancelled(
    booking: dict,
    recipient_role: str,
    ad_text: Optional[str] = None,
) -> str:
    """Format booking_cancelled notification."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    if recipient_role == "client":
        lines = [
            f"❌ <b>Ваша запись отменена #{booking_id}</b>",
            "",
        ]
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        if b.get("service_name"):
            lines.append(f"💇 {b['service_name']}")
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        lines.extend(["", "Для новой записи используйте /start"])
    elif recipient_role == "specialist":
        lines = [
            f"❌ <b>Запись отменена #{booking_id}</b>",
            "",
        ]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("service_name"):
            lines.append(f"💇 {b['service_name']}")
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        if b.get("cancel_reason"):
            lines.append(f"📝 {b['cancel_reason']}")
    else:
        # admin
        lines = [
            f"❌ <b>Запись отменена #{booking_id}</b>",
            "",
        ]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        if b.get("service_name"):
            lines.append(f"💇 {b['service_name']}")
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        if b.get("specialist_name"):
            lines.append(f"👨‍💼 {b['specialist_name']}")
        if b.get("cancel_reason"):
            lines.append(f"📝 {b['cancel_reason']}")

    if ad_text:
        lines.extend(["", "---", ad_text])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# booking_rescheduled
# ─────────────────────────────────────────────────────────────────────────────

async def format_booking_rescheduled(
    booking: dict,
    recipient_role: str,
    old_datetime: Optional[str] = None,
    new_datetime: Optional[str] = None,
    ad_text: Optional[str] = None,
) -> str:
    """Format booking_rescheduled notification."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    old_dt = _format_dt(old_datetime) if old_datetime else "—"
    new_dt = _format_dt(new_datetime) if new_datetime else _format_dt(b.get("date_start", ""))

    if recipient_role == "client":
        lines = [
            f"🔄 <b>Ваша запись перенесена #{booking_id}</b>",
            "",
        ]
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        if b.get("service_name"):
            lines.append(f"💇 {b['service_name']}")
        lines.append(f"🕐 Было: {old_dt}")
        lines.append(f"🕐 Стало: {new_dt}")
        lines.extend(["", "Если время не подходит — свяжитесь с нами."])
    elif recipient_role == "specialist":
        lines = [
            f"🔄 <b>Запись перенесена #{booking_id}</b>",
            "",
        ]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("service_name"):
            lines.append(f"💇 {b['service_name']}")
        lines.append(f"🕐 Было: {old_dt}")
        lines.append(f"🕐 Стало: {new_dt}")
    else:
        # admin
        lines = [
            f"🔄 <b>Запись перенесена #{booking_id}</b>",
            "",
        ]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        if b.get("service_name"):
            lines.append(f"💇 {b['service_name']}")
        lines.append(f"🕐 Было: {old_dt}")
        lines.append(f"🕐 Стало: {new_dt}")
        if b.get("specialist_name"):
            lines.append(f"👨‍💼 {b['specialist_name']}")

    if ad_text:
        lines.extend(["", "---", ad_text])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

FORMATTERS = {
    "booking_created": format_booking_created,
    "booking_cancelled": format_booking_cancelled,
    "booking_rescheduled": format_booking_rescheduled,
}


async def format_event(
    event_type: str,
    booking: dict,
    recipient_role: str,
    ad_text: Optional[str] = None,
    **kwargs,
) -> str:
    """Format an event message for a specific recipient role."""
    formatter = FORMATTERS.get(event_type)
    if not formatter:
        return f"Event: {event_type} (no formatter)"

    if event_type == "booking_rescheduled":
        return await formatter(
            booking,
            recipient_role,
            old_datetime=kwargs.get("old_datetime"),
            new_datetime=kwargs.get("new_datetime"),
            ad_text=ad_text,
        )

    return await formatter(booking, recipient_role, ad_text=ad_text)
