"""
Message formatting for notification events.

Per event_type + per recipient_role formatting.
HTML parse_mode for Telegram.
"""

import logging
from datetime import datetime
from urllib.parse import quote

from bot.app.i18n.loader import DEFAULT_LANG, t
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
            enriched["location_city"] = location.get("city", "")
            enriched["location_street"] = location.get("street", "")
            enriched["location_house"] = location.get("house", "")

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

    if booking.get("service_package_id"):
        package = await api.get_package(booking["service_package_id"])
        if package:
            enriched["package_name"] = package.get("name", "")
            enriched["package_duration"] = package.get("total_duration_min", 0)
            # Resolve individual services in package
            items = package.get("package_items") or []
            if isinstance(items, str):
                import json as _json
                try:
                    items = _json.loads(items)
                except Exception:
                    items = []
            svc_details = []
            for item in items:
                svc = await api.get_service(item["service_id"])
                if svc:
                    svc_details.append({
                        "name": svc.get("name", ""),
                        "duration_min": svc.get("duration_min", 0),
                    })
            enriched["package_services"] = svc_details

    return enriched


def _append_service_lines(lines: list[str], b: dict, lang: str, with_duration: bool = True) -> None:
    """Append service + package lines to notification."""
    minutes = t("common:minutes", lang)
    if b.get("package_name"):
        dur = b.get("package_duration") or b.get("duration_minutes", "")
        line = f"💇 {b['package_name']}"
        if with_duration and dur:
            line += f" · {dur} {minutes}"
        lines.append(line)
        for svc in b.get("package_services", []):
            svc_line = f"    ▸ {svc['name']}"
            if with_duration and svc.get("duration_min"):
                svc_line += f" {svc['duration_min']} {minutes}"
            lines.append(svc_line)
    elif b.get("service_name"):
        dur = b.get("service_duration", "")
        line = f"💇 {b['service_name']}"
        if with_duration and dur:
            line += f" · {dur} {minutes}"
        lines.append(line)


def build_address_text(b: dict) -> str:
    """Build address string from location fields: 'г. Чехов, Церковная горка, 1'."""
    parts = []
    city = b.get("location_city", "")
    if city:
        parts.append(f"г. {city}")
    street = b.get("location_street", "")
    house = b.get("location_house", "")
    if street and house:
        parts.append(f"{street}, {house}")
    elif street:
        parts.append(street)
    return ", ".join(parts)


def build_maps_url(address: str) -> str:
    """Build Yandex Maps search URL from address string."""
    return f"https://yandex.ru/maps/?text={quote(address)}"


def _append_address_line(lines: list[str], b: dict) -> None:
    """Append address with Yandex Maps link as the last line."""
    address = build_address_text(b)
    if address:
        url = build_maps_url(address)
        lines.append(f'📌 <a href="{url}">{address}</a>')


# ─────────────────────────────────────────────────────────────────────────────
# booking_created
# ─────────────────────────────────────────────────────────────────────────────

async def format_booking_created(
    booking: dict,
    recipient_role: str,
    ad_text: str | None = None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Format booking_created notification."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    if recipient_role == "client":
        title = t("notify:created:title:client", lang)
        lines = [f"<b>{title} #{booking_id}</b>", ""]
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        _append_service_lines(lines, b, lang)
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        if b.get("specialist_name"):
            lines.append(f"👨‍💼 {b['specialist_name']}")
        _append_address_line(lines, b)
    elif recipient_role == "specialist":
        title = t("notify:created:title", lang)
        lines = [f"{title} <b>#{booking_id}</b>", ""]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("client_phone"):
            lines.append(f"📞 {b['client_phone']}")
        _append_service_lines(lines, b, lang)
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
    else:
        # admin / default
        title = t("notify:created:title", lang)
        lines = [f"{title} <b>#{booking_id}</b>", ""]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("client_phone"):
            lines.append(f"📞 {b['client_phone']}")
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        _append_service_lines(lines, b, lang)
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
    ad_text: str | None = None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Format booking_cancelled notification."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    if recipient_role == "client":
        title = t("notify:cancelled:title:client", lang)
        lines = [f"<b>{title} #{booking_id}</b>", ""]
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        _append_service_lines(lines, b, lang, with_duration=False)
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        _append_address_line(lines, b)
        lines.extend(["", t("notify:cancelled:new_booking", lang)])
    elif recipient_role == "specialist":
        title = t("notify:cancelled:title", lang)
        lines = [f"{title} <b>#{booking_id}</b>", ""]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        _append_service_lines(lines, b, lang, with_duration=False)
        if b.get("date_start"):
            lines.append(f"🕐 {_format_dt(b['date_start'])}")
        if b.get("cancel_reason"):
            lines.append(f"📝 {b['cancel_reason']}")
    else:
        # admin
        title = t("notify:cancelled:title", lang)
        lines = [f"{title} <b>#{booking_id}</b>", ""]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        _append_service_lines(lines, b, lang, with_duration=False)
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
    old_datetime: str | None = None,
    new_datetime: str | None = None,
    ad_text: str | None = None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Format booking_rescheduled notification."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    old_dt = _format_dt(old_datetime) if old_datetime else "—"
    new_dt = _format_dt(new_datetime) if new_datetime else _format_dt(b.get("date_start", ""))
    was = t("notify:rescheduled:was", lang)
    now = t("notify:rescheduled:now", lang)

    if recipient_role == "client":
        title = t("notify:rescheduled:title:client", lang)
        lines = [f"<b>{title} #{booking_id}</b>", ""]
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        _append_service_lines(lines, b, lang, with_duration=False)
        lines.append(f"🕐 {was}: {old_dt}")
        lines.append(f"🕐 {now}: {new_dt}")
        _append_address_line(lines, b)
        lines.extend(["", t("notify:rescheduled:contact_us", lang)])
    elif recipient_role == "specialist":
        title = t("notify:rescheduled:title", lang)
        lines = [f"{title} <b>#{booking_id}</b>", ""]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        _append_service_lines(lines, b, lang, with_duration=False)
        lines.append(f"🕐 {was}: {old_dt}")
        lines.append(f"🕐 {now}: {new_dt}")
    else:
        # admin
        title = t("notify:rescheduled:title", lang)
        lines = [f"{title} <b>#{booking_id}</b>", ""]
        if b.get("client_name"):
            lines.append(f"👤 {b['client_name']}")
        if b.get("location_name"):
            lines.append(f"📍 {b['location_name']}")
        _append_service_lines(lines, b, lang, with_duration=False)
        lines.append(f"🕐 {was}: {old_dt}")
        lines.append(f"🕐 {now}: {new_dt}")
        if b.get("specialist_name"):
            lines.append(f"👨‍💼 {b['specialist_name']}")

    if ad_text:
        lines.extend(["", "---", ad_text])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# booking_done (completion confirmation)
# ─────────────────────────────────────────────────────────────────────────────

async def format_booking_done(
    booking: dict,
    recipient_role: str,
    ad_text: str | None = None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Format booking_done notification — card + confirmation question."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    lines = [
        f"{t('notify:done:title', lang)} <b>#{booking_id}</b>",
        "",
    ]

    if b.get("client_name"):
        lines.append(f"👤 {b['client_name']}")
    if b.get("client_phone"):
        lines.append(f"📞 {b['client_phone']}")
    if b.get("location_name"):
        lines.append(f"📍 {b['location_name']}")
    _append_service_lines(lines, b, lang)
    if b.get("date_start"):
        lines.append(f"🕐 {_format_dt(b['date_start'])}")
    if b.get("specialist_name"):
        lines.append(f"👨‍💼 {b['specialist_name']}")

    lines.extend(["", f"<b>{t('notify:done:question', lang)}</b>"])

    if ad_text:
        lines.extend(["", "---", ad_text])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# booking_reminder
# ─────────────────────────────────────────────────────────────────────────────

async def format_booking_reminder(
    booking: dict,
    recipient_role: str,
    ad_text: str | None = None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Format booking_reminder notification for client."""
    b = await _enrich_booking(booking)
    booking_id = b.get("id", "?")

    title = t("notify:reminder:title", lang)
    lines = [f"<b>{title} #{booking_id}</b>", ""]

    if b.get("location_name"):
        lines.append(f"📍 {b['location_name']}")
    _append_service_lines(lines, b, lang)
    if b.get("date_start"):
        lines.append(f"🕐 {_format_dt(b['date_start'])}")
    if b.get("specialist_name"):
        lines.append(f"👨‍💼 {b['specialist_name']}")
    if recipient_role == "client":
        _append_address_line(lines, b)

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
    "booking_done": format_booking_done,
    "booking_reminder": format_booking_reminder,
}


async def format_event(
    event_type: str,
    booking: dict,
    recipient_role: str,
    ad_text: str | None = None,
    lang: str = DEFAULT_LANG,
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
            lang=lang,
        )

    return await formatter(booking, recipient_role, ad_text=ad_text, lang=lang)
