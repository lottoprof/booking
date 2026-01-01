"""
bot/app/flows/admin/locations.py

FSM создания + редактирования + Список локаций с пагинацией.
"""

import logging
import json
import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.utils.schedule_helper import (
    DAYS,
    default_schedule,
    parse_time_input,
    format_day_value,
    format_schedule_compact,
)
from bot.app.keyboards.schedule import (
    schedule_days_inline,
    schedule_day_edit_inline,
)
from bot.app.keyboards.admin import admin_locations

logger = logging.getLogger(__name__)

# Пагинация
PAGE_SIZE = 5


# ==============================================================
# FSM States
# ==============================================================

class LocationCreate(StatesGroup):
    name = State()
    city = State()
    street = State()
    house = State()
    schedule = State()
    schedule_day = State()


class LocationEdit(StatesGroup):
    """FSM для редактирования локации."""
    name = State()
    city = State()
    address = State()      # улица + дом одним полем
    schedule = State()
    schedule_day = State()


# ==============================================================
# Inline keyboards
# ==============================================================

def cancel_inline(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="loc_create:cancel"
        )
    ]])


def locations_list_inline(
    locations: list[dict],
    page: int,
    lang: str
) -> InlineKeyboardMarkup:
    """Список локаций с пагинацией."""
    total = len(locations)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = locations[start:end]
    
    buttons = []
    
    # Кнопки локаций
    for loc in page_items:
        buttons.append([
            InlineKeyboardButton(
                text=t("admin:locations:item", lang) % loc["name"],
                callback_data=f"loc:view:{loc['id']}"
            )
        ])
    
    # Пагинация (если нужна)
    if total_pages > 1:
        nav_row = []
        
        # Кнопка "назад"
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text=t("common:prev", lang),
                callback_data=f"loc:page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="loc:noop"
            ))
        
        # Текущая страница
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="loc:noop"
        ))
        
        # Кнопка "вперёд"
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text=t("common:next", lang),
                callback_data=f"loc:page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="loc:noop"
            ))
        
        buttons.append(nav_row)
    
    # Кнопка "Назад" в Reply меню
    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="loc:back"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def location_view_inline(location: dict, lang: str) -> InlineKeyboardMarkup:
    """Карточка просмотра локации."""
    loc_id = location["id"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:location:edit", lang),
                callback_data=f"loc:edit:{loc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:location:delete", lang),
                callback_data=f"loc:delete:{loc_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data="loc:list:0"
            )
        ]
    ])


def location_delete_confirm_inline(loc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:yes", lang),
                callback_data=f"loc:delete_confirm:{loc_id}"
            ),
            InlineKeyboardButton(
                text=t("common:no", lang),
                callback_data=f"loc:view:{loc_id}"
            )
        ]
    ])


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


def edit_cancel_inline(loc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при редактировании поля."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"loc:edit:{loc_id}"
        )
    ]])


# ==============================================================
# Helper: build texts
# ==============================================================

def build_progress_text(data: dict, lang: str, prompt_key: str) -> str:
    """Строит текст с прогрессом заполнения (создание)."""
    lines = [t("admin:location:create_title", lang), ""]
    
    if data.get("name"):
        lines.append(f"📍 {data['name']}")
    if data.get("city"):
        lines.append(f"🏙 {data['city']}")
    if data.get("street"):
        s = data["street"]
        if data.get("house"):
            s += f", {data['house']}"
        lines.append(f"🏠 {s}")
    
    lines.append("")
    lines.append(t(prompt_key, lang))
    
    return "\n".join(lines)


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
        except:
            pass
    
    return "\n".join(lines)


def build_edit_text(loc: dict, changes: dict, lang: str) -> str:
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
        except:
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
        lines.append("")
        lines.append("✏️ " + ", ".join(_get_changed_field_names(changes, lang)))
    
    return "\n".join(lines)


def _get_changed_field_names(changes: dict, lang: str) -> list[str]:
    """Возвращает читаемые имена изменённых полей."""
    names = []
    if "name" in changes:
        names.append(t("admin:location:edit_name", lang).replace("✏️ ", ""))
    if "city" in changes:
        names.append(t("admin:location:edit_city", lang).replace("✏️ ", ""))
    if "street" in changes or "house" in changes:
        names.append(t("admin:location:edit_addr", lang).replace("✏️ ", ""))
    if "work_schedule" in changes:
        names.append(t("admin:location:edit_sched", lang).replace("📅 ", ""))
    return names


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    """Setup router with dependencies."""
    
    router = Router(name="locations")
    logger.info("=== locations.setup() called, creating router ===")

    # ==========================================================
    # LIST: показать список локаций
    # ==========================================================

    async def show_list(message: Message, page: int = 0):
        """Показать список локаций (вызывается из admin_reply)."""
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        locations = await api.get_locations()
        total = len(locations)
        
        if total == 0:
            text = t("admin:locations:empty", lang)
        else:
            text = t("admin:locations:list_title", lang) % total
        
        kb = locations_list_inline(locations, page, lang)
        await mc.show_inline(message, text, kb)

    router.show_list = show_list

    # ==========================================================
    # LIST: pagination callback
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:page:"))
    async def list_page(callback: CallbackQuery):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        locations = await api.get_locations()
        total = len(locations)
        
        if total == 0:
            text = t("admin:locations:empty", lang)
        else:
            text = t("admin:locations:list_title", lang) % total
        
        kb = locations_list_inline(locations, page, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "loc:list:0")
    async def list_first_page(callback: CallbackQuery):
        """Вернуться к первой странице списка."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        locations = await api.get_locations()
        total = len(locations)
        
        if total == 0:
            text = t("admin:locations:empty", lang)
        else:
            text = t("admin:locations:list_title", lang) % total
        
        kb = locations_list_inline(locations, 0, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "loc:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    # ==========================================================
    # LIST: back to Reply menu
    # ==========================================================

    @router.callback_query(F.data == "loc:back")
    async def list_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()  # очищаем FSM на всякий случай
        await mc.back_to_reply(
            callback.message,
            admin_locations(lang),
            title=t("admin:locations:title", lang)
        )
        await callback.answer()

    # ==========================================================
    # VIEW: карточка локации
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:view:"))
    async def view_location(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        # Очищаем FSM при возврате на просмотр (сброс редактирования)
        await state.clear()
        
        location = await api.get_location(loc_id)
        if not location:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        text = build_location_view_text(location, lang)
        kb = location_view_inline(location, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ==========================================================
    # DELETE: подтверждение
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:delete:"))
    async def delete_confirm(callback: CallbackQuery):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        location = await api.get_location(loc_id)
        if not location:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        text = t("admin:location:confirm_delete", lang) % location["name"]
        kb = location_delete_confirm_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("loc:delete_confirm:"))
    async def delete_execute(callback: CallbackQuery):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        success = await api.delete_location(loc_id)
        if success:
            await callback.answer(t("admin:location:deleted", lang))
        else:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        # Вернуться к списку
        locations = await api.get_locations()
        total = len(locations)
        
        if total == 0:
            text = t("admin:locations:empty", lang)
        else:
            text = t("admin:locations:list_title", lang) % total
        
        kb = locations_list_inline(locations, 0, lang)
        await mc.edit_inline(callback.message, text, kb)

    # ==========================================================
    # EDIT: показать экран редактирования
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:edit:"))
    async def edit_location(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        location = await api.get_location(loc_id)
        if not location:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        # Получаем текущие изменения из FSM (если есть)
        data = await state.get_data()
        
        # Если это новый вход в редактирование — инициализируем
        if data.get("edit_loc_id") != loc_id:
            await state.update_data(
                edit_loc_id=loc_id,
                original=location,
                changes={}
            )
            data = await state.get_data()
        
        changes = data.get("changes", {})
        text = build_edit_text(location, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ==========================================================
    # EDIT: name
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:edit_name:"))
    async def edit_name_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.name)
        
        text = t("admin:location:enter_name", lang)
        kb = edit_cancel_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.message(LocationEdit.name)
    async def edit_name_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()
        
        if len(name) < 2:
            err_msg = await message.answer(t("admin:location:error_name", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except:
                pass
            return
        
        data = await state.get_data()
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        changes["name"] = name
        
        await state.update_data(changes=changes)
        await state.set_state(None)  # выходим из FSM state
        
        # Возвращаемся на экран редактирования
        location = data.get("original", {})
        text = build_edit_text(location, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        try:
            await message.delete()
        except:
            pass
        
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: city
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:edit_city:"))
    async def edit_city_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.city)
        
        text = t("admin:location:enter_city", lang)
        kb = edit_cancel_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.message(LocationEdit.city)
    async def edit_city_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        city = message.text.strip()
        
        if len(city) < 2:
            err_msg = await message.answer(t("admin:location:error_city", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except:
                pass
            return
        
        data = await state.get_data()
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        changes["city"] = city
        
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        location = data.get("original", {})
        text = build_edit_text(location, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        try:
            await message.delete()
        except:
            pass
        
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: address (street + house одним полем)
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:edit_addr:"))
    async def edit_addr_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.address)
        
        text = t("admin:location:enter_addr", lang)
        kb = edit_cancel_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.message(LocationEdit.address)
    async def edit_addr_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        addr = message.text.strip()
        
        if not addr:
            try:
                await message.delete()
            except:
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
        
        location = data.get("original", {})
        text = build_edit_text(location, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        try:
            await message.delete()
        except:
            pass
        
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: schedule
    # ==========================================================

    @router.callback_query(F.data.startswith("loc:edit_sched:"))
    async def edit_sched_start(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        changes = data.get("changes", {})
        location = data.get("original", {})
        
        # Берём график из changes или из original
        if "work_schedule" in changes:
            schedule = changes["work_schedule"]
        else:
            try:
                ws = location.get("work_schedule", "{}")
                schedule = json.loads(ws) if isinstance(ws, str) else ws
            except:
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
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    @router.message(LocationEdit.schedule_day)
    async def edit_sched_time_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text_input = message.text.strip()
        
        result = parse_time_input(text_input)
        
        if result == "error":
            try:
                await message.delete()
            except:
                pass
            err_msg = await message.answer(t("schedule:invalid", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            return
        
        data = await state.get_data()
        day = data.get("editing_day")
        schedule = data.get("edit_schedule", {})
        schedule[day] = result
        
        await state.update_data(edit_schedule=schedule)
        await state.set_state(LocationEdit.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_edit_sched")
        
        try:
            await message.delete()
        except:
            pass
        
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

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
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data == "loc_edit_sched:back")
    async def edit_sched_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationEdit.schedule)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_edit_sched")
        
        await callback.message.edit_text(text, reply_markup=kb)
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
        
        location = data.get("original", {})
        text = build_edit_text(location, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "loc_edit_sched:cancel")
    async def edit_sched_cancel(callback: CallbackQuery, state: FSMContext):
        """Отменить редактирование графика, вернуться на экран редактирования."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        loc_id = data.get("edit_loc_id")
        changes = data.get("changes", {})
        location = data.get("original", {})
        
        await state.set_state(None)
        
        text = build_edit_text(location, changes, lang)
        kb = location_edit_inline(loc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ==========================================================
    # SAVE: применить все изменения
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
        location = await api.get_location(loc_id)
        if location:
            text = build_location_view_text(location, lang)
            kb = location_view_inline(location, lang)
            await mc.edit_inline(callback.message, text, kb)

    # ==========================================================
    # START CREATE
    # ==========================================================
    
    async def start_create(message: Message, state: FSMContext):
        """Entry point — вызывается из admin_reply."""
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        logger.info(f"start_create called, setting state LocationCreate.name")
        
        await state.set_state(LocationCreate.name)
        await state.update_data(lang=lang, schedule=default_schedule())
        
        text = f"{t('admin:location:create_title', lang)}\n\n{t('admin:location:enter_name', lang)}"
        await mc.show_inline(message, text, cancel_inline(lang))
    
    router.start_create = start_create

    # ==========================================================
    # Helper: send tracked inline
    # ==========================================================

    async def send_step(message: Message, text: str, kb: InlineKeyboardMarkup):
        """Отправить inline с трекингом для очистки."""
        chat_id = message.chat.id
        bot = message.bot
        
        try:
            await message.delete()
        except:
            pass
        
        return await mc.send_inline_in_flow(bot, chat_id, text, kb)

    # ==========================================================
    # NAME → CITY (CREATE)
    # ==========================================================
    
    @router.message(LocationCreate.name)
    async def process_name(message: Message, state: FSMContext):
        logger.info(f"process_name handler called with text: {message.text}")
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()
        
        if len(name) < 2:
            err_msg = await message.answer(t("admin:location:error_name", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except:
                pass
            return
        
        await state.update_data(name=name)
        await state.set_state(LocationCreate.city)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:location:enter_city")
        await send_step(message, text, cancel_inline(lang))

    # ==========================================================
    # CITY → STREET (CREATE)
    # ==========================================================
    
    @router.message(LocationCreate.city)
    async def process_city(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        city = message.text.strip()
        
        if len(city) < 2:
            err_msg = await message.answer(t("admin:location:error_city", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except:
                pass
            return
        
        await state.update_data(city=city)
        await state.set_state(LocationCreate.street)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:location:enter_street")
        await send_step(message, text, cancel_inline(lang))

    # ==========================================================
    # STREET → HOUSE (CREATE)
    # ==========================================================
    
    @router.message(LocationCreate.street)
    async def process_street(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        street = message.text.strip()
        if not street:
            return
        
        await state.update_data(street=street)
        await state.set_state(LocationCreate.house)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:location:enter_house")
        await send_step(message, text, cancel_inline(lang))

    # ==========================================================
    # HOUSE → SCHEDULE (CREATE)
    # ==========================================================
    
    @router.message(LocationCreate.house)
    async def process_house(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        house = message.text.strip()
        if not house:
            return
        
        await state.update_data(house=house)
        await state.set_state(LocationCreate.schedule)
        
        data = await state.get_data()
        schedule = data.get("schedule", default_schedule())
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_sched")
        await send_step(message, text, kb)

    # ==========================================================
    # SCHEDULE: day selected (CREATE)
    # ==========================================================
    
    @router.callback_query(F.data.startswith("loc_sched:day:"))
    async def schedule_day_selected(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("schedule", {})
        current = format_day_value(schedule.get(day), lang)
        
        await state.set_state(LocationCreate.schedule_day)
        await state.update_data(editing_day=day)
        
        day_name = t(f"day:{day}:full", lang)
        text = (
            f"{day_name}\n"
            f"{t('schedule:current', lang) % current}\n\n"
            f"{t('schedule:enter_time', lang)}"
        )
        
        kb = schedule_day_edit_inline(day, schedule, lang, prefix="loc_sched")
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    # ==========================================================
    # SCHEDULE_DAY: text input (time) (CREATE)
    # ==========================================================
    
    @router.message(LocationCreate.schedule_day)
    async def process_schedule_time(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text_input = message.text.strip()
        
        result = parse_time_input(text_input)
        
        if result == "error":
            try:
                await message.delete()
            except:
                pass
            # Трекаем сообщение об ошибке для очистки
            err_msg = await message.answer(t("schedule:invalid", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            return
        
        data = await state.get_data()
        day = data.get("editing_day")
        schedule = data.get("schedule", {})
        schedule[day] = result
        
        await state.update_data(schedule=schedule)
        await state.set_state(LocationCreate.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_sched")
        await send_step(message, text, kb)

    # ==========================================================
    # SCHEDULE_DAY: day off button (CREATE)
    # ==========================================================
    
    @router.callback_query(F.data.startswith("loc_sched:dayoff:"))
    async def schedule_day_off(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("schedule", {})
        schedule[day] = None
        
        await state.update_data(schedule=schedule)
        await state.set_state(LocationCreate.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_sched")
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    # ==========================================================
    # SCHEDULE: back from day edit (CREATE)
    # ==========================================================
    
    @router.callback_query(F.data == "loc_sched:back")
    async def schedule_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(LocationCreate.schedule)
        
        data = await state.get_data()
        schedule = data.get("schedule", {})
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_sched")
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    # ==========================================================
    # SCHEDULE: save → create location (CREATE)
    # ==========================================================
    
    @router.callback_query(F.data == "loc_sched:save")
    async def schedule_save(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        
        company = await api.get_company()
        if not company:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        location = await api.create_location(
            company_id=company["id"],
            name=data["name"],
            city=data["city"],
            street=data.get("street"),
            house=data.get("house"),
            work_schedule=json.dumps(data.get("schedule", {}))
        )
        
        if not location:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        await state.clear()
        await callback.answer(t("admin:location:created", lang) % data["name"])
        
        await mc.back_to_reply(
            callback.message,
            admin_locations(lang),
            title=t("admin:locations:title", lang)
        )

    # ==========================================================
    # CANCEL: any step (CREATE)
    # ==========================================================
    
    @router.callback_query(F.data == "loc_create:cancel")
    @router.callback_query(F.data == "loc_sched:cancel")
    async def cancel_create(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.clear()
        await callback.answer()
        
        await mc.back_to_reply(
            callback.message,
            admin_locations(lang),
            title=t("admin:locations:title", lang)
        )

    logger.info(f"=== locations router configured ===")
    return router

