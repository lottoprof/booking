"""
bot/app/flows/admin/locations_edit.py

EDIT-FSM for Locations (admin).
Вынесено из locations.py без изменения бизнес-логики.

Правила:
- FSM в Redis (через общий aiogram storage)
- PATCH только diff (changes)
- Inline-only
- Не управляет Reply/menu_context (это делает locations.py/admin_reply.py)

Особенности:
- Редактирование графика — отдельный экран с днями недели
- Адрес редактируется одним полем (улица, дом)
"""

import json
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.i18n.loader import DEFAULT_LANG, t, t_all
from bot.app.keyboards.admin import admin_locations
from bot.app.keyboards.schedule import (
    schedule_day_edit_inline,
    schedule_days_inline,
)
from bot.app.utils.api import api
from bot.app.utils.schedule_helper import (
    default_schedule,
    format_day_value,
    format_schedule_compact,
    parse_time_input,
)
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)


# ==============================================================
# FSM States (EDIT)
# ==============================================================

class LocationEdit(StatesGroup):
    """FSM для редактирования локации."""
    name = State()
    city = State()
    address = State()      # улица + дом одним полем
    schedule = State()
    schedule_day = State()


# ==============================================================
# Inline keyboards for EDIT
# ==============================================================

def location_edit_inline(loc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Экран редактирования локации."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:location:edit_name", lang),
                callback_data=f"loc:edit_name:{loc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:location:edit_city", lang),
                callback_data=f"loc:edit_city:{loc_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("admin:location:edit_addr", lang),
                callback_data=f"loc:edit_addr:{loc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:location:edit_sched", lang),
                callback_data=f"loc:edit_sched:{loc_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("common:save", lang),
                callback_data=f"loc:save:{loc_id}"
            ),
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data=f"loc:view:{loc_id}"
            ),
        ],
    ])


def location_edit_cancel_inline(loc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при редактировании поля."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"loc:edit:{loc_id}"
        )
    ]])


# ==============================================================
# Helpers: texts
# ==============================================================

def build_location_view_text(loc: dict, lang: str) -> str:
    """Текст карточки локации."""
    lines = [t("admin:location:view_title", lang) % loc["name"], ""]
    
    # Город
    if loc.get("city"):
        lines.append(f"🏙 {loc['city']}")
    
    # Адрес
    if loc.get("street"):
        addr = loc["street"]
        if loc.get("house"):
            addr += f", {loc['house']}"
        lines.append(f"🏠 {addr}")
    
    # График
    if loc.get("work_schedule"):
        try:
            schedule = json.loads(loc["work_schedule"]) if isinstance(loc["work_schedule"], str) else loc["work_schedule"]
            if schedule:
                schedule_str = format_schedule_compact(schedule, lang)
                lines.append(f"📅 {schedule_str}")
        except Exception:
            pass
    
    return "\n".join(lines)


def build_location_edit_text(loc: dict, changes: dict, lang: str) -> str:
    """
    Текст экрана редактирования.
    Показывает текущие значения + изменения из changes.
    """
    # Применяем изменения для отображения
    name = changes.get("name", loc.get("name", ""))
    city = changes.get("city", loc.get("city", ""))
    
    # Адрес: если есть изменение — берём из changes, иначе из loc
    if "street" in changes or "house" in changes:
        street = changes.get("street", loc.get("street", ""))
        house = changes.get("house", loc.get("house", ""))
    else:
        street = loc.get("street", "")
        house = loc.get("house", "")
    
    # График
    if "work_schedule" in changes:
        schedule = changes["work_schedule"]
    else:
        try:
            ws = loc.get("work_schedule", "{}")
            schedule = json.loads(ws) if isinstance(ws, str) else ws
        except Exception:
            schedule = {}
    
    lines = [t("admin:location:edit_title", lang), ""]
    lines.append(f"📍 {name}")
    lines.append(f"🏙 {city}")
    
    if street:
        addr = street
        if house:
            addr += f", {house}"
        lines.append(f"🏠 {addr}")
    
    if schedule:
        schedule_str = format_schedule_compact(schedule, lang)
        lines.append(f"📅 {schedule_str}")
    
    # Показываем что изменено
    if changes:
        changed_names = _get_changed_field_names(changes, lang)
        if changed_names:
            lines.append("")
            lines.append("✏️ " + ", ".join(changed_names))
    
    return "\n".join(lines)


def _get_changed_field_names(changes: dict, lang: str) -> list[str]:
    """Возвращает читаемые имена изменённых полей."""
    field_map = {
        "name": "admin:location:edit_name",
        "city": "admin:location:edit_city",
        "street": "admin:location:edit_addr",
        "house": "admin:location:edit_addr",
        "work_schedule": "admin:location:edit_sched",
    }
    
    names = []
    seen = set()
    for field, key in field_map.items():
        if field in changes and key not in seen:
            name = t(key, lang)
            for emoji in ["✏️ ", "📝 ", "📅 ", "🏠 ", "🏙 "]:
                name = name.replace(emoji, "")
            names.append(name)
            seen.add(key)
    
    return names


# ==============================================================
# Entry point (called from locations.py delegate)
# ==============================================================

async def start_location_edit(
    *,
    mc,
    callback: CallbackQuery,
    state: FSMContext,
    loc_id: int
) -> None:
    """
    Entry point редактирования локации.
    """
    lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
    
    loc = await api.get_location(loc_id)
    if not loc:
        await callback.answer(t("common:error", lang), show_alert=True)
        return
    
    data = await state.get_data()
    
    # Если новый вход или другой loc_id — инициализируем заново
    if data.get("edit_loc_id") != loc_id:
        await state.update_data(
            edit_loc_id=loc_id,
            original=loc,
            changes={}
        )
        data = await state.get_data()
    
    changes = data.get("changes", {})
    text = build_location_edit_text(loc, changes, lang)
    kb = location_edit_inline(loc_id, lang)
    
    await mc.edit_inline_input(callback.message, text, kb)
    await callback.answer()


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    """
    Setup router with dependencies.
    Возвращает Router с EDIT handlers.
    """
    
    router = Router(name="locations_edit")
    logger.info("=== locations_edit.setup() called ===")
    
    # ==========================================================
    # Reply "Back" escape hatch for EDIT FSM
    # ==========================================================
    
    @router.message(F.text.in_(t_all("admin:locations:back")), LocationEdit.name)
    @router.message(F.text.in_(t_all("admin:locations:back")), LocationEdit.city)
    @router.message(F.text.in_(t_all("admin:locations:back")), LocationEdit.address)
    @router.message(F.text.in_(t_all("admin:locations:back")), LocationEdit.schedule)
    @router.message(F.text.in_(t_all("admin:locations:back")), LocationEdit.schedule_day)
    async def edit_fsm_back_escape(message: Message, state: FSMContext):
        """Escape hatch: Reply Back во время Edit FSM → отмена и возврат."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.show(
            message,
            admin_locations(lang),
            title=t("admin:locations:title", lang),
            menu_context="locations",
        )
    
    # ==========================================================
    # EDIT: name
    # ==========================================================
    
    @router.callback_query(F.data.startswith("loc:edit_name:"))
    async def edit_name_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.name)
        
        text = t("admin:location:enter_name", lang)
        kb = location_edit_cancel_inline(loc_id, lang)
        
        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()
    
    @router.message(LocationEdit.name)
    async def edit_name_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()
        
        if len(name) < 2:
            data = await state.get_data()
            loc_id = data.get("edit_loc_id")
            await mc.show_inline_input(message, t("admin:location:error_name", lang), location_edit_cancel_inline(loc_id, lang))
            return
        
        data = await state.get_data()
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        changes["name"] = name
        
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        loc = data.get("original", {})
        text = build_location_edit_text(loc, changes, lang)
        kb = location_edit_inline(loc_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: city
    # ==========================================================
    
    @router.callback_query(F.data.startswith("loc:edit_city:"))
    async def edit_city_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.city)
        
        text = t("admin:location:enter_city", lang)
        kb = location_edit_cancel_inline(loc_id, lang)
        
        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()
    
    @router.message(LocationEdit.city)
    async def edit_city_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        city = message.text.strip()
        
        if len(city) < 2:
            data = await state.get_data()
            loc_id = data.get("edit_loc_id")
            await mc.show_inline_input(message, t("admin:location:error_city", lang), location_edit_cancel_inline(loc_id, lang))
            return
        
        data = await state.get_data()
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        changes["city"] = city
        
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        loc = data.get("original", {})
        text = build_location_edit_text(loc, changes, lang)
        kb = location_edit_inline(loc_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: address (street + house одним полем)
    # ==========================================================
    
    @router.callback_query(F.data.startswith("loc:edit_addr:"))
    async def edit_addr_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.address)
        
        text = t("admin:location:enter_addr", lang)
        kb = location_edit_cancel_inline(loc_id, lang)
        
        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()
    
    @router.message(LocationEdit.address)
    async def edit_addr_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        addr = message.text.strip()
        
        if not addr:
            try:
                await message.delete()
            except Exception:
                pass
            return
        
        # Парсим адрес: "улица, дом" или просто "улица"
        if "," in addr:
            parts = addr.split(",", 1)
            street = parts[0].strip()
            house = parts[1].strip()
        else:
            street = addr
            house = ""
        
        data = await state.get_data()
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        changes["street"] = street
        changes["house"] = house
        
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        loc = data.get("original", {})
        text = build_location_edit_text(loc, changes, lang)
        kb = location_edit_inline(loc_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: schedule
    # ==========================================================
    
    @router.callback_query(F.data.startswith("loc:edit_sched:"))
    async def edit_sched_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])  # noqa: F841
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        changes = data.get("changes", {})
        loc = data.get("original", {})
        
        # Берём график из changes или из original
        if "work_schedule" in changes:
            schedule = changes["work_schedule"]
        else:
            try:
                ws = loc.get("work_schedule", "{}")
                schedule = json.loads(ws) if isinstance(ws, str) else ws
            except Exception:
                schedule = default_schedule()
        
        await state.set_state(LocationEdit.schedule)
        await state.update_data(edit_schedule=schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_edit_sched")
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data.startswith("loc_edit_sched:day:"))
    async def edit_sched_day_selected(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        current = format_day_value(schedule.get(day), lang)
        
        await state.set_state(LocationEdit.schedule_day)
        await state.update_data(editing_day=day)
        
        day_name = t(f"day:{day}:full", lang)
        text = (
            f"{day_name}\n"
            f"{t('schedule:current', lang) % current}\n\n"
            f"{t('schedule:enter_time', lang)}"
        )
        
        kb = schedule_day_edit_inline(day, schedule, lang, prefix="loc_edit_sched")
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.message(LocationEdit.schedule_day)
    async def edit_sched_time_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text_input = message.text.strip()
        
        result = parse_time_input(text_input)
        
        if result == "error":
            data = await state.get_data()
            loc_id = data.get("edit_loc_id")
            await mc.show_inline_input(message, t("schedule:invalid", lang), location_edit_cancel_inline(loc_id, lang))
            return
        
        data = await state.get_data()
        day = data.get("editing_day")
        schedule = data.get("edit_schedule", {})
        schedule[day] = result
        
        await state.update_data(edit_schedule=schedule)
        await state.set_state(LocationEdit.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_edit_sched")

        await mc.show_inline_readonly(message, text, kb)
    
    @router.callback_query(F.data.startswith("loc_edit_sched:dayoff:"))
    async def edit_sched_day_off(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        schedule[day] = None
        
        await state.update_data(edit_schedule=schedule)
        await state.set_state(LocationEdit.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_edit_sched")
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "loc_edit_sched:back")
    async def edit_sched_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.schedule)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_edit_sched")
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "loc_edit_sched:save")
    async def edit_sched_save(callback: CallbackQuery, state: FSMContext):
        """Сохранить график в changes и вернуться на экран редактирования."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        
        changes["work_schedule"] = schedule
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        loc = data.get("original", {})
        text = build_location_edit_text(loc, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "loc_edit_sched:cancel")
    async def edit_sched_cancel(callback: CallbackQuery, state: FSMContext):
        """Отменить редактирование графика."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        loc = data.get("original", {})
        
        await state.set_state(None)
        
        text = build_location_edit_text(loc, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ==========================================================
    # SAVE: применить все изменения полей
    # ==========================================================
    
    @router.callback_query(F.data.startswith("loc:save:"))
    async def save_location(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        changes = data.get("changes", {})
        
        if not changes:
            await callback.answer(t("admin:location:no_changes", lang))
            return
        
        # Подготовка данных для PATCH
        patch_data = {}
        
        if "name" in changes:
            patch_data["name"] = changes["name"]
        if "city" in changes:
            patch_data["city"] = changes["city"]
        if "street" in changes:
            patch_data["street"] = changes["street"]
        if "house" in changes:
            patch_data["house"] = changes["house"]
        if "work_schedule" in changes:
            patch_data["work_schedule"] = json.dumps(changes["work_schedule"])
        
        if patch_data:
            result = await api.update_location(loc_id, **patch_data)
            if not result:
                await callback.answer(t("common:error", lang), show_alert=True)
                return
        
        await state.clear()
        await callback.answer(t("admin:location:saved", lang))
        
        # Показать обновлённую карточку
        loc = await api.get_location(loc_id)
        if loc:
            from .locations import location_view_inline
            text = build_location_view_text(loc, lang)
            kb = location_view_inline(loc, lang)
            await mc.edit_inline(callback.message, text, kb)
    
    logger.info("=== locations_edit router configured ===")
    return router

