"""
bot/app/flows/admin/locations.py

FSM создания локации.
"""

import logging
import json
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


# ==============================================================
# Helper: build progress text
# ==============================================================

def build_progress_text(data: dict, lang: str, prompt_key: str) -> str:
    """Строит текст с прогрессом заполнения."""
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


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    """Setup router with dependencies."""
    
    router = Router(name="locations")
    logger.info("=== locations.setup() called, creating router ===")

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
    
    # Expose for admin_reply
    router.start_create = start_create

    # ==========================================================
    # Helper: send tracked inline
    # ==========================================================

    async def send_step(message: Message, text: str, kb: InlineKeyboardMarkup):
        """Отправить inline с трекингом для очистки."""
        chat_id = message.chat.id
        bot = message.bot
        
        # Удалить сообщение пользователя
        try:
            await message.delete()
        except:
            pass
        
        # Отправить и трекать
        return await mc.send_inline_in_flow(bot, chat_id, text, kb)

    # ==========================================================
    # NAME → CITY
    # ==========================================================
    
    @router.message(LocationCreate.name)
    async def process_name(message: Message, state: FSMContext):
        logger.info(f"process_name handler called with text: {message.text}")
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()
        if not name:
            return
        
        await state.update_data(name=name)
        await state.set_state(LocationCreate.city)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:location:enter_city")
        await send_step(message, text, cancel_inline(lang))

    # ==========================================================
    # CITY → STREET
    # ==========================================================
    
    @router.message(LocationCreate.city)
    async def process_city(message: Message, state: FSMContext):
        logger.info(f"process_city handler called")
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        city = message.text.strip()
        if not city:
            return
        
        await state.update_data(city=city)
        await state.set_state(LocationCreate.street)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:location:enter_street")
        await send_step(message, text, cancel_inline(lang))

    # ==========================================================
    # STREET → HOUSE
    # ==========================================================
    
    @router.message(LocationCreate.street)
    async def process_street(message: Message, state: FSMContext):
        logger.info(f"process_street handler called")
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
    # HOUSE → SCHEDULE
    # ==========================================================
    
    @router.message(LocationCreate.house)
    async def process_house(message: Message, state: FSMContext):
        logger.info(f"process_house handler called")
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
    # SCHEDULE: day selected
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
    # SCHEDULE_DAY: text input (time)
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
            # Отправляем ошибку как отдельное сообщение (не трекаем — временное)
            err_msg = await message.answer(t("schedule:invalid", lang))
            # Можно удалить через секунду, но пока оставим
            return
        
        # result is dict or None (day off)
        data = await state.get_data()
        day = data.get("editing_day")
        schedule = data.get("schedule", {})
        schedule[day] = result
        
        await state.update_data(schedule=schedule)
        await state.set_state(LocationCreate.schedule)
        
        # Return to schedule view
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="loc_sched")
        await send_step(message, text, kb)

    # ==========================================================
    # SCHEDULE_DAY: day off button
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
    # SCHEDULE: back from day edit
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
    # SCHEDULE: save → create location
    # ==========================================================
    
    @router.callback_query(F.data == "loc_sched:save")
    async def schedule_save(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        
        company = await api.get_company()
        if not company:
            await callback.answer("Error: no company", show_alert=True)
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
            await callback.answer("Error creating location", show_alert=True)
            return
        
        await state.clear()
        await callback.answer(t("admin:location:created", lang) % data["name"])
        
        # Возврат в Reply меню (удалит все tracked inline)
        await mc.back_to_reply(
            callback.message,
            admin_locations(lang),
            title=t("admin:locations:title", lang)
        )

    # ==========================================================
    # CANCEL: any step
    # ==========================================================
    
    @router.callback_query(F.data == "loc_create:cancel")
    @router.callback_query(F.data == "loc_sched:cancel")
    async def cancel_create(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.clear()
        await callback.answer()
        
        # Возврат в Reply меню (удалит все tracked inline)
        await mc.back_to_reply(
            callback.message,
            admin_locations(lang),
            title=t("admin:locations:title", lang)
        )

    logger.info(f"=== locations router configured, handlers count: {len(router.message.handlers)} ===")
    return router

