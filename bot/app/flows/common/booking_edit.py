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

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.utils.api import api

logger = logging.getLogger(__name__)

router = Router(name="booking_edit")


class RescheduleStates(StatesGroup):
    """FSM for rescheduling a booking."""
    select_date = State()
    select_time = State()
    confirm = State()


# ─────────────────────────────────────────────────────────────────────────────
# Edit Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bke:menu:"))
async def show_edit_menu(callback: CallbackQuery):
    """Show edit menu for a booking."""
    parts = callback.data.split(":")
    booking_id = int(parts[2])
    return_to = parts[3] if len(parts) > 3 else "hide"

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    text = _format_edit_view(booking)
    keyboard = build_edit_menu_keyboard(booking_id, return_to)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Cancel Flow
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bke:cancel:"))
async def confirm_cancel(callback: CallbackQuery):
    """Show cancellation confirmation prompt."""
    parts = callback.data.split(":")
    booking_id = int(parts[2])
    return_to = ":".join(parts[3:]) if len(parts) > 3 else "hide"

    text = "❓ Отменить запись?\n\nЭто действие нельзя отменить."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, отменить",
                callback_data=f"bke:confirm_cancel:{booking_id}:{return_to}",
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=f"bke:menu:{booking_id}:{return_to}",
            ),
        ]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("bke:confirm_cancel:"))
async def do_cancel(callback: CallbackQuery):
    """Execute booking cancellation."""
    parts = callback.data.split(":")
    booking_id = int(parts[2])
    return_to = ":".join(parts[3:]) if len(parts) > 3 else "hide"

    # Cancel via backend (will emit booking_cancelled event)
    result = await api.cancel_booking(
        booking_id,
        reason="Отменено через бот",
        initiated_by_user_id=None,  # TODO: pass actual initiator
        initiated_by_role=None,
    )

    if result is None:
        await callback.answer("Ошибка при отмене", show_alert=True)
        return

    text = f"❌ Запись #{booking_id} отменена"

    if return_to == "hide":
        await callback.message.edit_text(text, reply_markup=None)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data=return_to)]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)

    await callback.answer("Запись отменена")


# ─────────────────────────────────────────────────────────────────────────────
# Reschedule Flow
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bke:reschedule:"))
async def start_reschedule(callback: CallbackQuery, state: FSMContext):
    """Start reschedule flow — show available dates."""
    parts = callback.data.split(":")
    booking_id = int(parts[2])

    booking = await api.get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
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
        await callback.answer("Нет доступных дат", show_alert=True)
        await state.clear()
        return

    text = "📅 Выберите новую дату:"
    keyboard = _build_date_keyboard(calendar["days"])

    await callback.message.edit_text(text, reply_markup=keyboard)
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

    # Get available time slots for this date
    slots = await api.get_slots_day(location_id, service_id, date_str)
    if not slots or not slots.get("available_times"):
        await callback.answer("Нет доступного времени на эту дату", show_alert=True)
        return

    await state.update_data(reschedule_date=date_str)
    await state.set_state(RescheduleStates.select_time)

    text = f"🕐 Выберите время на {date_str}:"
    keyboard = _build_time_keyboard(slots["available_times"], date_str)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(
    RescheduleStates.select_time,
    F.data.startswith("bke:time:"),
)
async def select_time(callback: CallbackQuery, state: FSMContext):
    """Handle time selection — show confirmation."""
    time_str = callback.data.split(":", 2)[2]
    data = await state.get_data()

    await state.update_data(reschedule_time=time_str)
    await state.set_state(RescheduleStates.confirm)

    old_dt = data.get("reschedule_old_datetime", "")
    new_dt = f"{data['reschedule_date']}T{time_str}"

    text = (
        f"Подтвердите перенос:\n\n"
        f"🕐 Было: {_format_dt(old_dt)}\n"
        f"🕐 Стало: {_format_dt(new_dt)}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data="bke:confirm_reschedule",
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="bke:cancel_reschedule",
            ),
        ]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
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

    if result:
        text = f"✅ Запись #{booking_id} перенесена\n\n🕐 {_format_dt(new_start)}"
    else:
        text = f"❌ Ошибка при переносе записи #{booking_id}"

    await callback.message.edit_text(text, reply_markup=None)
    await callback.answer()


@router.callback_query(
    RescheduleStates.confirm,
    F.data == "bke:cancel_reschedule",
)
async def cancel_reschedule(callback: CallbackQuery, state: FSMContext):
    """Cancel the reschedule flow."""
    await state.clear()
    await callback.message.edit_text("Перенос отменён.", reply_markup=None)
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_dt(iso_str: str) -> str:
    """Format ISO datetime to '28.01.2026 14:00'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", ""))
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_str


def _format_edit_view(booking: dict) -> str:
    """Format booking info for edit menu."""
    booking_id = booking.get("id", "?")
    lines = [f"📝 <b>Запись #{booking_id}</b>", ""]

    if booking.get("date_start"):
        lines.append(f"🕐 {_format_dt(booking['date_start'])}")
    lines.append(f"📋 Статус: {booking.get('status', '—')}")

    return "\n".join(lines)


def build_edit_menu_keyboard(
    booking_id: int,
    return_to: str,
    allow_reschedule: bool = True,
) -> InlineKeyboardMarkup:
    """Build edit menu keyboard."""
    buttons = [
        [InlineKeyboardButton(
            text="❌ Отменить запись",
            callback_data=f"bke:cancel:{booking_id}:{return_to}",
        )],
    ]

    if allow_reschedule:
        buttons.append([InlineKeyboardButton(
            text="🕐 Изменить время",
            callback_data=f"bke:reschedule:{booking_id}",
        )])

    back_cb = return_to if return_to != "hide" else f"bke:back:{booking_id}"
    buttons.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=back_cb,
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_date_keyboard(
    days: list[dict],
    max_buttons: int = 12,
) -> InlineKeyboardMarkup:
    """Build calendar date selection keyboard."""
    buttons = []
    row = []

    for day in days[:max_buttons]:
        if not day.get("has_slots"):
            continue

        date_str = day["date"]
        # Format: "28 Jan"
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
        text="❌ Отмена",
        callback_data="bke:cancel_reschedule",
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_time_keyboard(
    times: list,
    date_str: str,
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
        text="❌ Отмена",
        callback_data="bke:cancel_reschedule",
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
