"""
Callback handlers for booking notification buttons.

Admin/manager callbacks (bkn:*):
- bkn:edit:{booking_id}    — Edit booking → delegate to common/booking_edit
- bkn:hide:{booking_id}    — Hide (delete) notification message
- bkn:back:{booking_id}    — Return to notification view
- bkn:done_yes:{booking_id} — Confirm service delivered → status "done"
- bkn:done_no:{booking_id}  — Service not provided → status "no_show"

Client callbacks (bkr:*):
- bkr:confirm:{booking_id} — Client confirms attendance → status "confirmed"
- bkr:hide:{booking_id}    — Client hides reminder notification (no status change)
- bkr:cancel:{booking_id}  — Client cancels booking → status "cancelled" (legacy)
"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.utils.api import api

logger = logging.getLogger(__name__)


def setup(mc):
    """Setup admin booking notification router with MenuController."""
    router = Router(name="booking_notify")

    @router.callback_query(F.data.startswith("bkn:hide:"))
    async def handle_hide(callback: CallbackQuery):
        """Delete the notification message."""
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer(t("common:hidden", DEFAULT_LANG))

    @router.callback_query(F.data.startswith("bkn:edit:"))
    async def handle_edit(callback: CallbackQuery):
        """Open edit menu — render directly, Back returns to notification view."""
        booking_id = int(callback.data.split(":")[2])
        return_to = f"bkn:back:{booking_id}"

        booking = await api.get_booking(booking_id)
        if not booking:
            await callback.answer(t("common:not_found", DEFAULT_LANG), show_alert=True)
            return

        from bot.app.flows.common.booking_edit import _format_edit_view, build_edit_menu_keyboard

        text = _format_edit_view(booking)
        keyboard = build_edit_menu_keyboard(booking_id, return_to)

        await mc.edit_inline(callback.message, text, keyboard, parse_mode="HTML")
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
                t(f"notify:status:{booking.get('status')}", lang), show_alert=True
            )
        else:
            result = await api.complete_booking(booking_id)
            if result:
                await callback.answer(t("notify:done:confirmed", lang), show_alert=True)
            else:
                await callback.answer(t("common:error", lang), show_alert=True)

        # Always delete — admin made a decision
        try:
            await callback.message.delete()
        except Exception:
            pass

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
                t(f"notify:status:{booking.get('status')}", lang), show_alert=True
            )
        else:
            result = await api.update_booking(booking_id, status="no_show")
            if result:
                await callback.answer(
                    t("notify:done:not_provided", lang), show_alert=True
                )
            else:
                await callback.answer(t("common:error", lang), show_alert=True)

        # Always delete — admin made a decision
        try:
            await callback.message.delete()
        except Exception:
            pass

    @router.callback_query(F.data.startswith("bkn:back:"))
    async def handle_back(callback: CallbackQuery):
        """Return to the original notification view."""
        booking_id = int(callback.data.split(":")[2])

        booking = await api.get_booking(booking_id)
        if not booking:
            await callback.answer(t("common:not_found", DEFAULT_LANG), show_alert=True)
            return

        text = await _format_notification(booking)
        keyboard = _build_notify_keyboard(booking_id)

        await mc.edit_inline(callback.message, text, keyboard, parse_mode="HTML")
        await callback.answer()

    return router


async def _format_notification(booking: dict, lang: str = DEFAULT_LANG) -> str:
    """Format the notification message (simplified view)."""
    booking_id = booking.get("id", "?")
    title = t("notify:booking:title", lang)
    lines = [f"{title} <b>#{booking_id}</b>", ""]

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

    status_label = t("notify:status_label", lang)
    lines.append(f"{status_label} {booking.get('status', '—')}")

    return "\n".join(lines)


def _build_notify_keyboard(booking_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    """Build notification keyboard."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Client reminder callbacks (bkr:*)
# ─────────────────────────────────────────────────────────────────────────────

client_notify_router = Router(name="client_booking_notify")


@client_notify_router.callback_query(F.data.startswith("bkr:hide:"))
async def handle_reminder_hide(callback: CallbackQuery):
    """Client hides reminder notification."""
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer(t("common:hidden", DEFAULT_LANG))


@client_notify_router.callback_query(F.data.startswith("bkr:confirm:"))
async def handle_reminder_confirm(callback: CallbackQuery):
    """Client confirms attendance → status 'confirmed'."""
    booking_id = int(callback.data.split(":")[2])
    lang = DEFAULT_LANG

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer(t("common:error", lang), show_alert=True)
        return

    if booking.get("status") in ("confirmed", "done", "no_show", "cancelled"):
        await callback.answer(
            t("notify:reminder:processed", lang), show_alert=True
        )
        return

    result = await api.update_booking(booking_id, status="confirmed")
    if result:
        await callback.answer(
            t("notify:reminder:confirmed", lang), show_alert=True
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer(t("common:error", lang), show_alert=True)


@client_notify_router.callback_query(F.data.startswith("bkr:cancel:"))
async def handle_reminder_cancel(callback: CallbackQuery):
    """Client cancels booking → status 'cancelled'."""
    booking_id = int(callback.data.split(":")[2])
    lang = DEFAULT_LANG

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer(t("common:error", lang), show_alert=True)
        return

    if booking.get("status") in ("done", "no_show", "cancelled"):
        await callback.answer(
            t("notify:reminder:processed", lang), show_alert=True
        )
        return

    result = await api.update_booking(booking_id, status="cancelled")
    if result:
        await callback.answer(
            t("notify:reminder:cancelled", lang), show_alert=True
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer(t("common:error", lang), show_alert=True)
