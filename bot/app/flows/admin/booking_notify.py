"""
Callback handlers for booking notification buttons.

Callbacks:
- bkn:edit:{booking_id}  — Edit booking → delegate to common/booking_edit
- bkn:hide:{booking_id}  — Hide (delete) notification message
- bkn:back:{booking_id}  — Return to notification view
"""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from bot.app.utils.api import api

logger = logging.getLogger(__name__)

router = Router(name="booking_notify")


@router.callback_query(F.data.startswith("bkn:hide:"))
async def handle_hide(callback: CallbackQuery):
    """Delete the notification message."""
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Скрыто")


@router.callback_query(F.data.startswith("bkn:edit:"))
async def handle_edit(callback: CallbackQuery):
    """Open edit menu — redirect to common booking_edit module."""
    booking_id = int(callback.data.split(":")[2])

    # Rewrite callback_data to common module format
    # return_to = bkn:back:{booking_id} so "Back" returns to notification view
    callback.data = f"bke:menu:{booking_id}:bkn:back:{booking_id}"

    from bot.app.flows.common.booking_edit import show_edit_menu
    await show_edit_menu(callback)


@router.callback_query(F.data.startswith("bkn:back:"))
async def handle_back(callback: CallbackQuery):
    """Return to the original notification view."""
    booking_id = int(callback.data.split(":")[2])

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    text = await _format_notification(booking)
    keyboard = _build_notify_keyboard(booking_id)

    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


async def _format_notification(booking: dict) -> str:
    """Format the notification message (simplified view)."""
    booking_id = booking.get("id", "?")
    lines = [f"📅 <b>Запись #{booking_id}</b>", ""]

    if booking.get("client_id"):
        client = await api.get_user(booking["client_id"])
        if client:
            name = f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()
            lines.append(f"👤 {name or '—'}")
            if client.get("phone"):
                lines.append(f"📞 {client['phone']}")

    if booking.get("date_start"):
        try:
            dt = datetime.fromisoformat(booking["date_start"].replace("Z", ""))
            lines.append(f"🕐 {dt.strftime('%d.%m.%Y %H:%M')}")
        except Exception:
            lines.append(f"🕐 {booking['date_start']}")

    lines.append(f"📋 {booking.get('status', '—')}")

    return "\n".join(lines)


def _build_notify_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Build notification keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✏️ Редактировать",
                callback_data=f"bkn:edit:{booking_id}",
            ),
            InlineKeyboardButton(
                text="🙈 Скрыть",
                callback_data=f"bkn:hide:{booking_id}",
            ),
        ]
    ])
