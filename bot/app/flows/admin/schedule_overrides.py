"""
bot/app/flows/admin/schedule_overrides.py

Изменение расписания локации/специалиста через calendar_override.
"""

import re
import logging
from datetime import datetime, date, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

# Регулярка для формата времени HH:MM-HH:MM
TIME_PATTERN = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")

# Ключи дней недели
WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class ScheduleOverride(StatesGroup):
    time_input = State()


# ==============================================================
# Helpers
# ==============================================================

def get_next_week_days() -> list[date]:
    """Возвращает следующие 7 дней начиная с сегодня."""
    today = date.today()
    return [today + timedelta(days=i) for i in range(7)]


def is_working_day(day: date, schedule: dict) -> bool:
    """Проверяет, рабочий ли день по базовому расписанию."""
    day_key = WEEKDAY_KEYS[day.weekday()]
    day_schedule = schedule.get(day_key)
    return day_schedule is not None and day_schedule != [] and day_schedule != ""


def format_day_schedule(schedule: dict, day: date) -> str:
    """Форматирует расписание дня (например, '09:00-18:00')."""
    day_key = WEEKDAY_KEYS[day.weekday()]
    day_schedule = schedule.get(day_key)

    if not day_schedule:
        return ""

    # Dict: {'start': '10:00', 'end': '20:00'}
    if isinstance(day_schedule, dict):
        start = day_schedule.get("start", "")
        end = day_schedule.get("end", "")
        if start and end:
            return f"{start}-{end}"
        return ""

    # Строка: "09:00-18:00"
    if isinstance(day_schedule, str):
        return day_schedule

    # Список: ["09:00", "18:00"]
    if isinstance(day_schedule, list) and len(day_schedule) >= 2:
        return f"{day_schedule[0]}-{day_schedule[1]}"

    return ""


def parse_time_input(text: str) -> tuple[bool, str]:
    """
    Парсит ввод времени.

    Returns:
        (is_day_off, time_str или None)
    """
    text = text.strip()

    if text == "0":
        return True, None

    match = TIME_PATTERN.match(text)
    if match:
        h1, m1, h2, m2 = match.groups()
        # Простая валидация
        if 0 <= int(h1) <= 23 and 0 <= int(m1) <= 59 and 0 <= int(h2) <= 23 and 0 <= int(m2) <= 59:
            return False, text

    return None, None  # Невалидный ввод


def _format_name(user: dict) -> str:
    """Форматирует имя пользователя."""
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


# ==============================================================
# Keyboards
# ==============================================================

def kb_choose_target(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа объекта."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:schovr:target_location", lang),
                callback_data="schovr:type:loc"
            ),
            InlineKeyboardButton(
                text=t("admin:schovr:target_specialist", lang),
                callback_data="schovr:type:spec"
            ),
        ],
        [InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="schovr:back_menu"
        )]
    ])


def kb_locations_list(locations: list[dict], lang: str) -> InlineKeyboardMarkup:
    """Клавиатура списка локаций."""
    rows = []
    for loc in locations:
        rows.append([InlineKeyboardButton(
            text=f"📍 {loc['name']}",
            callback_data=f"schovr:loc:{loc['id']}"
        )])
    rows.append([InlineKeyboardButton(
        text=t("common:back", lang),
        callback_data="schovr:back_type"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_specialists_list(specialists: list[dict], lang: str) -> InlineKeyboardMarkup:
    """Клавиатура списка специалистов."""
    rows = []
    for spec in specialists:
        name = spec.get("_display_name", spec.get("display_name", "—"))
        rows.append([InlineKeyboardButton(
            text=f"👤 {name}",
            callback_data=f"schovr:spec:{spec['id']}"
        )])
    rows.append([InlineKeyboardButton(
        text=t("common:back", lang),
        callback_data="schovr:back_type"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_week_calendar(
    days: list[date],
    schedule: dict,
    overrides: list[dict],
    target_type: str,
    target_id: int,
    lang: str,
) -> InlineKeyboardMarkup:
    """7-дневный календарь с текущим расписанием."""
    buttons = []

    for day in days:
        day_key = WEEKDAY_KEYS[day.weekday()]
        day_name = t(f"day:{day_key}", lang)
        day_date = day.strftime("%d.%m")

        # Проверяем, есть ли override на этот день
        override = None
        for ovr in overrides:
            ovr_start = ovr.get("date_start")
            ovr_end = ovr.get("date_end")
            if ovr_start and ovr_end:
                # Парсим даты
                try:
                    if isinstance(ovr_start, str):
                        ovr_start = datetime.strptime(ovr_start, "%Y-%m-%d").date()
                    if isinstance(ovr_end, str):
                        ovr_end = datetime.strptime(ovr_end, "%Y-%m-%d").date()
                    if ovr_start <= day <= ovr_end:
                        override = ovr
                        break
                except Exception:
                    pass

        # Определяем текст кнопки — БЕЗ времени
        if override and override.get("override_kind") == "day_off":
            text = f"😴 {day_name} {day_date}"
        elif not is_working_day(day, schedule) and not override:
            text = f"😴 {day_name} {day_date}"
        else:
            text = f"{day_name} {day_date}"

        buttons.append(InlineKeyboardButton(
            text=text,
            callback_data=f"schovr:day:{target_type}:{target_id}:{day.isoformat()}"
        ))

    # Группируем по 2 в ряд
    rows = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i+2])

    # Кнопка "Назад"
    rows.append([InlineKeyboardButton(
        text=t("common:back", lang),
        callback_data=f"schovr:back_{target_type}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_time_input(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура для ввода времени."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="schovr:cancel_input"
        )]
    ])


def kb_confirm_override(
    target_type: str,
    target_id: int,
    date_str: str,
    is_day_off: bool,
    time_str: str,
    lang: str,
) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения изменения."""
    # Заменяем : на . в времени, чтобы не ломать split(":")
    encoded_time = time_str.replace(":", ".") if time_str else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:yes", lang),
                callback_data=f"schovr:confirm:{target_type}:{target_id}:{date_str}:{'off' if is_day_off else encoded_time}"
            ),
            InlineKeyboardButton(
                text=t("common:no", lang),
                callback_data=f"schovr:day:{target_type}:{target_id}:{date_str}"
            ),
        ]
    ])


# ==============================================================
# Setup
# ==============================================================

def setup(menu_controller, api):
    """
    Args:
        menu_controller: MenuController
        api: ApiClient
    Returns:
        Router
    """
    router = Router(name="schedule_overrides")
    mc = menu_controller

    # Локальный кэш для хранения данных между callback'ами
    router._override_cache = {}

    # ----------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------

    async def show_overrides(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()

        text = t("admin:schovr:choose_target", lang)
        kb = kb_choose_target(lang)
        await mc.show_inline_input(message, text, kb)

    router.show_overrides = show_overrides

    # ----------------------------------------------------------
    # Callbacks: выбор типа объекта
    # ----------------------------------------------------------

    @router.callback_query(F.data == "schovr:back_menu")
    async def back_to_menu(callback: CallbackQuery, state: FSMContext):
        from bot.app.keyboards.admin import admin_schedule
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.back_to_reply(
            callback.message,
            admin_schedule(lang),
            title=t("admin:schedule:title", lang),
            menu_context="schedule"
        )
        await callback.answer()

    @router.callback_query(F.data == "schovr:back_type")
    async def back_to_type(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        text = t("admin:schovr:choose_target", lang)
        kb = kb_choose_target(lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "schovr:type:loc")
    async def choose_location(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        locations = await api.get_locations()
        if not locations:
            await callback.answer(t("admin:schovr:no_locations", lang), show_alert=True)
            return

        text = t("admin:schovr:select_location", lang)
        kb = kb_locations_list(locations, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "schovr:type:spec")
    async def choose_specialist(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        specialists = await api.get_specialists()
        if not specialists:
            await callback.answer(t("admin:schovr:no_specialists", lang), show_alert=True)
            return

        # Добавляем имена
        for spec in specialists:
            if spec.get("display_name"):
                spec["_display_name"] = spec["display_name"]
            else:
                user = await api.get_user(spec.get("user_id"))
                spec["_display_name"] = _format_name(user) if user else "—"

        text = t("admin:schovr:select_specialist", lang)
        kb = kb_specialists_list(specialists, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callbacks: выбор локации/специалиста -> календарь
    # ----------------------------------------------------------

    async def _show_location_calendar(callback: CallbackQuery, location_id: int, skip_answer: bool = False):
        """Показывает календарь локации."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        location = await api.get_location(location_id)
        if not location:
            if not skip_answer:
                await callback.answer(t("common:not_found", lang), show_alert=True)
            return

        schedule = location.get("work_schedule", {})
        if isinstance(schedule, str):
            import json
            try:
                schedule = json.loads(schedule)
            except Exception:
                schedule = {}

        overrides = await api.get_calendar_overrides(
            target_type="location",
            target_id=location_id
        )

        days = get_next_week_days()

        # Кэшируем для повторного использования
        cache_key = callback.message.chat.id
        router._override_cache[cache_key] = {
            "target_type": "loc",
            "target_id": location_id,
            "schedule": schedule,
            "name": location.get("name", ""),
        }

        text = t("admin:schovr:calendar_title", lang)
        kb = kb_week_calendar(days, schedule, overrides, "loc", location_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        if not skip_answer:
            await callback.answer()

    async def _show_specialist_calendar(callback: CallbackQuery, specialist_id: int, skip_answer: bool = False):
        """Показывает календарь специалиста."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        specialist = await api.get_specialist(specialist_id)
        if not specialist:
            if not skip_answer:
                await callback.answer(t("common:not_found", lang), show_alert=True)
            return

        schedule = specialist.get("work_schedule", {})
        if isinstance(schedule, str):
            import json
            try:
                schedule = json.loads(schedule)
            except Exception:
                schedule = {}

        overrides = await api.get_calendar_overrides(
            target_type="specialist",
            target_id=specialist_id
        )

        days = get_next_week_days()

        # Получаем имя
        if specialist.get("display_name"):
            name = specialist["display_name"]
        else:
            user = await api.get_user(specialist.get("user_id"))
            name = _format_name(user) if user else "—"

        # Кэшируем
        cache_key = callback.message.chat.id
        router._override_cache[cache_key] = {
            "target_type": "spec",
            "target_id": specialist_id,
            "schedule": schedule,
            "name": name,
        }

        text = t("admin:schovr:calendar_title", lang)
        kb = kb_week_calendar(days, schedule, overrides, "spec", specialist_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        if not skip_answer:
            await callback.answer()

    @router.callback_query(F.data.startswith("schovr:loc:"))
    async def show_location_calendar(callback: CallbackQuery, state: FSMContext):
        location_id = int(callback.data.split(":")[2])
        await _show_location_calendar(callback, location_id)

    @router.callback_query(F.data.startswith("schovr:spec:"))
    async def show_specialist_calendar(callback: CallbackQuery, state: FSMContext):
        specialist_id = int(callback.data.split(":")[2])
        await _show_specialist_calendar(callback, specialist_id)

    @router.callback_query(F.data == "schovr:back_loc")
    async def back_to_loc_list(callback: CallbackQuery, state: FSMContext):
        await choose_location(callback, state)

    @router.callback_query(F.data == "schovr:back_spec")
    async def back_to_spec_list(callback: CallbackQuery, state: FSMContext):
        await choose_specialist(callback, state)

    # ----------------------------------------------------------
    # Callbacks: выбор дня -> ввод времени
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("schovr:day:"))
    async def select_day(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        target_type = parts[2]  # loc или spec
        target_id = int(parts[3])
        date_str = parts[4]

        # Получаем текущее расписание из кэша
        cache = router._override_cache.get(callback.message.chat.id, {})
        schedule = cache.get("schedule", {})

        # Парсим дату
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        current_schedule = format_day_schedule(schedule, selected_date)

        if not current_schedule:
            current_schedule = t("admin:schovr:day_off", lang)

        # Сохраняем в state
        await state.set_state(ScheduleOverride.time_input)
        await state.update_data(
            target_type=target_type,
            target_id=target_id,
            selected_date=date_str,
        )

        text = f"{t('admin:schovr:enter_time', lang)}\n\n{t('admin:schovr:current', lang, current_schedule)}"
        await mc.edit_inline_input(callback.message, text, kb_time_input(lang))
        await callback.answer()

    @router.callback_query(F.data == "schovr:cancel_input")
    async def cancel_input(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        target_type = data.get("target_type", "loc")
        target_id = data.get("target_id")

        await state.clear()

        if target_type == "loc" and target_id:
            await _show_location_calendar(callback, target_id)
        elif target_type == "spec" and target_id:
            await _show_specialist_calendar(callback, target_id)
        else:
            await back_to_type(callback, state)

    # ----------------------------------------------------------
    # FSM: ввод времени
    # ----------------------------------------------------------

    @router.message(ScheduleOverride.time_input)
    async def process_time_input(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text = message.text.strip()

        try:
            await message.delete()
        except Exception:
            pass

        is_day_off, time_str = parse_time_input(text)

        if is_day_off is None:
            # Невалидный ввод
            err = await message.answer(t("admin:schovr:invalid_time", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return

        data = await state.get_data()
        target_type = data.get("target_type")
        target_id = data.get("target_id")
        date_str = data.get("selected_date")

        await state.clear()

        # Показываем подтверждение
        if is_day_off:
            change_text = t("admin:schovr:day_off", lang)
        else:
            change_text = time_str

        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        day_key = WEEKDAY_KEYS[selected_date.weekday()]
        day_name = t(f"day:{day_key}:full", lang)

        confirm_text = f"{t('admin:schovr:confirm', lang)}\n\n{day_name} {selected_date.strftime('%d.%m')}: {change_text}"
        kb = kb_confirm_override(target_type, target_id, date_str, is_day_off, time_str or "", lang)

        await mc.send_inline_in_flow(message.bot, message.chat.id, confirm_text, kb)

    # ----------------------------------------------------------
    # Callbacks: подтверждение
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("schovr:confirm:"))
    async def confirm_override(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        target_type = parts[2]  # loc или spec
        target_id = int(parts[3])
        date_str = parts[4]
        time_or_off = parts[5] if len(parts) > 5 else "off"

        is_day_off = time_or_off == "off"

        # Декодируем время (. -> :)
        if not is_day_off:
            time_or_off = time_or_off.replace(".", ":")

        # Определяем target_type для API
        api_target_type = "location" if target_type == "loc" else "specialist"

        # Сначала удаляем существующие overrides на эту дату
        existing = await api.get_calendar_overrides(
            target_type=api_target_type,
            target_id=target_id
        )
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        for ovr in existing:
            try:
                ovr_start = ovr.get("date_start")
                ovr_end = ovr.get("date_end")
                if isinstance(ovr_start, str):
                    ovr_start = datetime.strptime(ovr_start, "%Y-%m-%d").date()
                if isinstance(ovr_end, str):
                    ovr_end = datetime.strptime(ovr_end, "%Y-%m-%d").date()
                if ovr_start <= selected_date <= ovr_end:
                    await api.delete_calendar_override(ovr["id"])
            except Exception as e:
                logger.warning(f"Failed to delete override {ovr.get('id')}: {e}")

        # Создаём новый override
        # block с reason = время (day_off, block — допустимые значения)
        override_kind = "day_off" if is_day_off else "block"
        reason = None if is_day_off else time_or_off

        result = await api.create_calendar_override(
            target_type=api_target_type,
            target_id=target_id,
            date_start=date_str,
            date_end=date_str,
            override_kind=override_kind,
            reason=reason,
        )

        if result:
            await callback.answer(t("admin:schovr:changed", lang), show_alert=True)
        else:
            await callback.answer(t("admin:schovr:error", lang), show_alert=True)

        # Возвращаемся к календарю
        if target_type == "loc":
            await _show_location_calendar(callback, target_id, skip_answer=True)
        else:
            await _show_specialist_calendar(callback, target_id, skip_answer=True)

    return router
