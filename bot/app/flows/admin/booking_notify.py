"""
Callback handlers for booking notification buttons.

Callbacks:
- bkn:edit:{booking_id}    — Edit booking → delegate to common/booking_edit
- bkn:hide:{booking_id}    — Hide (delete) notification message
- bkn:back:{booking_id}    — Return to notification view
- bkn:done_yes:{booking_id} — Confirm service delivered → status "done"
- bkn:done_no:{booking_id}  — Service not provided → status "no_show"
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
from bot.app.i18n.loader import t, DEFAULT_LANG

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
    """Open edit menu — render directly, Back returns to notification view."""
    booking_id = int(callback.data.split(":")[2])
    return_to = f"bkn:back:{booking_id}"

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    from bot.app.flows.common.booking_edit import build_edit_menu_keyboard, _format_edit_view

    text = _format_edit_view(booking)
    keyboard = build_edit_menu_keyboard(booking_id, return_to)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("bkn:done_yes:"))
async def handle_done_yes(callback: CallbackQuery):
    """Confirm service was delivered — set status to 'done'."""
    booking_id = int(callback.data.split(":")[2])
    lang = DEFAULT_LANG

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer(t("common:error", lang), show_alert=True)
        return

    if booking.get("status") in ("done", "no_show", "cancelled"):
        await callback.answer(
            t("notify:done:already_processed", lang), show_alert=True
        )
        return

    result = await api.complete_booking(booking_id)
    if result:
        await callback.answer(t("notify:done:confirmed", lang), show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer(t("common:error", lang), show_alert=True)


@router.callback_query(F.data.startswith("bkn:done_no:"))
async def handle_done_no(callback: CallbackQuery):
    """Service was NOT provided — set status to 'no_show'."""
    booking_id = int(callback.data.split(":")[2])
    lang = DEFAULT_LANG

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer(t("common:error", lang), show_alert=True)
        return

    if booking.get("status") in ("done", "no_show", "cancelled"):
        await callback.answer(
            t("notify:done:already_processed", lang), show_alert=True
        )
        return

    result = await api.update_booking(booking_id, status="no_show")
    if result:
        await callback.answer(
            t("notify:done:not_provided", lang), show_alert=True
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer(t("common:error", lang), show_alert=True)


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
