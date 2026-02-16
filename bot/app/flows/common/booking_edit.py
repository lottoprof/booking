"""
Reusable booking edit module.

Used from:
- admin/booking_notify.py (notification callbacks)
- admin/clients.py (client bookings)
- specialist/bookings.py (own bookings)
- client/my_bookings.py (own bookings — cancel only)

Callbacks:
- bke:menu:{booking_id}:{return_to}        — Show edit menu
- bke:cancel:{booking_id}:{return_to}      — Confirm cancel prompt
- bke:confirm_cancel:{booking_id}:{return_to} — Execute cancel
- bke:reschedule:{booking_id}              — Start reschedule FSM
"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.utils.api import api

logger = logging.getLogger(__name__)


class RescheduleStates(StatesGroup):
    """FSM for rescheduling a booking."""
    select_date = State()
    select_time = State()
    confirm = State()


def setup(mc):
    """Setup booking edit router with MenuController."""
    router = Router(name="booking_edit")

    # ─────────────────────────────────────────────────────────────────────────
    # Edit Menu
    # ─────────────────────────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("bke:menu:"))
    async def show_edit_menu(callback: CallbackQuery):
        """Show edit menu for a booking."""
        parts = callback.data.split(":")
        booking_id = int(parts[2])
        return_to = parts[3] if len(parts) > 3 else "hide"

        lang = DEFAULT_LANG
        booking = await api.get_booking(booking_id)
        if not booking:
            await callback.answer(t("common:not_found", lang), show_alert=True)
            return

        if _is_expired(booking):
            await callback.answer(t("bke:expired", lang), show_alert=True)
            return

        text = _format_edit_view(booking, lang=lang)
        keyboard = build_edit_menu_keyboard(booking_id, return_to, lang=lang)

        await mc.edit_inline(callback.message, text, keyboard, parse_mode="HTML")
        await callback.answer()

    # ─────────────────────────────────────────────────────────────────────────
    # Cancel Flow
    # ─────────────────────────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("bke:cancel:"))
    async def confirm_cancel(callback: CallbackQuery):
        """Show cancellation confirmation prompt."""
        parts = callback.data.split(":")
        booking_id = int(parts[2])
        return_to = ":".join(parts[3:]) if len(parts) > 3 else "hide"
        lang = DEFAULT_LANG

        booking = await api.get_booking(booking_id)
        if _is_expired(booking or {}):
            await callback.answer(t("bke:expired", lang), show_alert=True)
            return

        text = t("bke:cancel_confirm", lang)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("bke:yes_cancel", lang),
                    callback_data=f"bke:confirm_cancel:{booking_id}:{return_to}",
                ),
                InlineKeyboardButton(
                    text=t("common:no", lang),
                    callback_data=f"bke:menu:{booking_id}:{return_to}",
                ),
            ]
        ])

        await mc.edit_inline(callback.message, text, keyboard)
        await callback.answer()

    @router.callback_query(F.data.startswith("bke:confirm_cancel:"))
    async def do_cancel(callback: CallbackQuery):
        """Execute booking cancellation."""
        parts = callback.data.split(":")
        booking_id = int(parts[2])
        return_to = ":".join(parts[3:]) if len(parts) > 3 else "hide"
        lang = DEFAULT_LANG

        # Cancel via backend (will emit booking_cancelled event)
        result = await api.cancel_booking(
            booking_id,
            reason=t("bke:cancelled_reason", lang),
            initiated_by_user_id=None,  # TODO: pass actual initiator
            initiated_by_role=None,
        )

        if result is None:
            await callback.answer(t("bke:cancel_error", lang), show_alert=True)
            return

        text = t("bke:cancelled", lang, booking_id)

        if return_to == "hide":
            await mc.edit_inline(
                callback.message, text,
                InlineKeyboardMarkup(inline_keyboard=[]),
            )
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("common:back", lang), callback_data=return_to)]
            ])
            await mc.edit_inline(callback.message, text, keyboard)

        await callback.answer(t("bke:cancelled_short", lang))

    # ─────────────────────────────────────────────────────────────────────────
    # Reschedule Flow
    # ─────────────────────────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("bke:reschedule:"))
    async def start_reschedule(callback: CallbackQuery, state: FSMContext):
        """Start reschedule flow — show available dates."""
        parts = callback.data.split(":")
        booking_id = int(parts[2])

        lang = DEFAULT_LANG
        booking = await api.get_booking(booking_id)
        if not booking:
            await callback.answer(t("common:not_found", lang), show_alert=True)
            return

        if _is_expired(booking):
            await callback.answer(t("bke:expired", lang), show_alert=True)
            return

        # Save context for FSM
        await state.update_data(
            reschedule_booking_id=booking_id,
            reschedule_location_id=booking["location_id"],
            reschedule_service_id=booking["service_id"],
            reschedule_old_datetime=booking["date_start"],
            reschedule_message_id=callback.message.message_id,
        )
        await state.set_state(RescheduleStates.select_date)

        # Show calendar
        calendar = await api.get_slots_calendar(booking["location_id"])
        if not calendar or not calendar.get("days"):
            await callback.answer(t("bke:no_dates", lang), show_alert=True)
            await state.clear()
            return

        text = t("bke:select_date", lang)
        keyboard = _build_date_keyboard(calendar["days"], lang=lang)

        await mc.edit_inline(callback.message, text, keyboard)
        await callback.answer()

    @router.callback_query(
        RescheduleStates.select_date,
        F.data.startswith("bke:date:"),
    )
    async def select_date(callback: CallbackQuery, state: FSMContext):
        """Handle date selection in reschedule flow."""
        date_str = callback.data.split(":", 2)[2]
        data = await state.get_data()

        location_id = data["reschedule_location_id"]
        service_id = data["reschedule_service_id"]

        lang = DEFAULT_LANG

        # Get available time slots for this date
        slots = await api.get_slots_day(location_id, service_id, date_str)
        if not slots or not slots.get("available_times"):
            await callback.answer(t("bke:no_times", lang), show_alert=True)
            return

        await state.update_data(reschedule_date=date_str)
        await state.set_state(RescheduleStates.select_time)

        text = t("bke:select_time", lang, date_str)
        keyboard = _build_time_keyboard(slots["available_times"], date_str, lang=lang)

        await mc.edit_inline(callback.message, text, keyboard)
        await callback.answer()

    @router.callback_query(
        RescheduleStates.select_time,
        F.data.startswith("bke:time:"),
    )
    async def select_time(callback: CallbackQuery, state: FSMContext):
        """Handle time selection — show confirmation."""
        time_str = callback.data.split(":", 2)[2]
        data = await state.get_data()

        lang = DEFAULT_LANG
        await state.update_data(reschedule_time=time_str)
        await state.set_state(RescheduleStates.confirm)

        old_dt = data.get("reschedule_old_datetime", "")
        new_dt = f"{data['reschedule_date']}T{time_str}"
        was = t("notify:rescheduled:was", lang)
        now = t("notify:rescheduled:now", lang)

        text = (
            f"{t('bke:confirm_reschedule', lang)}\n\n"
            f"🕐 {was}: {_format_dt(old_dt)}\n"
            f"🕐 {now}: {_format_dt(new_dt)}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common:confirm", lang),
                    callback_data="bke:confirm_reschedule",
                ),
                InlineKeyboardButton(
                    text=t("common:cancel", lang),
                    callback_data="bke:cancel_reschedule",
                ),
            ]
        ])

        await mc.edit_inline(callback.message, text, keyboard)
        await callback.answer()

    @router.callback_query(
        RescheduleStates.confirm,
        F.data == "bke:confirm_reschedule",
    )
    async def confirm_reschedule(callback: CallbackQuery, state: FSMContext):
        """Execute the reschedule."""
        data = await state.get_data()

        booking_id = data["reschedule_booking_id"]
        date_str = data["reschedule_date"]
        time_str = data["reschedule_time"]
        service_id = data["reschedule_service_id"]

        # Get service duration for date_end calculation
        service = await api.get_service(service_id)
        duration = service.get("duration_min", 60) if service else 60
        break_min = service.get("break_min", 0) if service else 0

        new_start = f"{date_str}T{time_str}"
        try:
            dt_start = datetime.fromisoformat(new_start)
            from datetime import timedelta
            dt_end = dt_start + timedelta(minutes=duration + break_min)
            new_end = dt_end.isoformat()
        except Exception:
            new_end = new_start

        # Update via backend (will emit booking_rescheduled event)
        result = await api.update_booking(
            booking_id,
            date_start=new_start,
            date_end=new_end,
        )

        await state.clear()
        lang = DEFAULT_LANG

        if result:
            text = t("bke:rescheduled", lang, booking_id) + f"\n\n🕐 {_format_dt(new_start)}"
        else:
            text = t("bke:reschedule_error", lang, booking_id)

        await mc.edit_inline(
            callback.message, text,
            InlineKeyboardMarkup(inline_keyboard=[]),
        )
        await callback.answer()

    @router.callback_query(
        RescheduleStates.confirm,
        F.data == "bke:cancel_reschedule",
    )
    async def cancel_reschedule(callback: CallbackQuery, state: FSMContext):
        """Cancel the reschedule flow."""
        await state.clear()
        await mc.edit_inline(
            callback.message,
            t("bke:reschedule_cancelled", DEFAULT_LANG),
            InlineKeyboardMarkup(inline_keyboard=[]),
        )
        await callback.answer()

    return router


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_expired(booking: dict) -> bool:
    """Check if booking's end time has already passed."""
    date_end = booking.get("date_end")
    if not date_end:
        return False
    try:
        dt_end = datetime.fromisoformat(date_end.replace("Z", ""))
        return datetime.utcnow() > dt_end
    except Exception:
        return False


def _format_dt(iso_str: str) -> str:
    """Format ISO datetime to '28.01.2026 14:00'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", ""))
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_str


def _format_edit_view(booking: dict, lang: str = DEFAULT_LANG) -> str:
    """Format booking info for edit menu."""
    booking_id = booking.get("id", "?")
    title = t("bke:edit_title", lang)
    lines = [f"{title} <b>#{booking_id}</b>", ""]

    if booking.get("date_start"):
        lines.append(f"🕐 {_format_dt(booking['date_start'])}")
    status_label = t("bke:status_label", lang)
    lines.append(f"{status_label}: {booking.get('status', '—')}")

    return "\n".join(lines)


def build_edit_menu_keyboard(
    booking_id: int,
    return_to: str,
    allow_reschedule: bool = True,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Build edit menu keyboard."""
    buttons = [
        [InlineKeyboardButton(
            text=t("bke:cancel_booking", lang),
            callback_data=f"bke:cancel:{booking_id}:{return_to}",
        )],
    ]

    if allow_reschedule:
        buttons.append([InlineKeyboardButton(
            text=t("bke:change_time", lang),
            callback_data=f"bke:reschedule:{booking_id}",
        )])

    back_cb = return_to if return_to != "hide" else f"bke:back:{booking_id}"
    buttons.append([InlineKeyboardButton(
        text=t("common:back", lang),
        callback_data=back_cb,
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_date_keyboard(
    days: list[dict],
    max_buttons: int = 12,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Build calendar date selection keyboard."""
    buttons = []
    row = []

    for day in days[:max_buttons]:
        if not day.get("has_slots"):
            continue

        date_str = day["date"]
        # Format: "28.01"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            label = dt.strftime("%d.%m")
        except Exception:
            label = date_str

        row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"bke:date:{date_str}",
        ))

        if len(row) == 4:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(
        text=t("common:cancel", lang),
        callback_data="bke:cancel_reschedule",
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_time_keyboard(
    times: list,
    date_str: str,
    lang: str = DEFAULT_LANG,
) -> InlineKeyboardMarkup:
    """Build time selection keyboard."""
    buttons = []
    row = []

    for time_entry in times:
        # time_entry can be a string "14:00" or dict with "time" key
        if isinstance(time_entry, dict):
            time_str = time_entry.get("time", "")
        else:
            time_str = str(time_entry)

        row.append(InlineKeyboardButton(
            text=time_str,
            callback_data=f"bke:time:{time_str}",
        ))

        if len(row) == 4:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(
        text=t("common:cancel", lang),
        callback_data="bke:cancel_reschedule",
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
