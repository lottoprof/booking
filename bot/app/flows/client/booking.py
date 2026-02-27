# bot/app/flows/client/booking.py
"""
FSM бронирования для клиента.

Flow:
1. Услуга (пагинация если > 5)
2. День (Level 1 из Redis)
3. Время + Специалист (Level 2)
4. [Phone Gate если нет телефона]
5. Подтверждение → POST /bookings
"""

import logging
import math
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ContentType, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.keyboards.common import request_phone_keyboard
from bot.app.utils.api import api
from bot.app.utils.phone_utils import (
    phone_required,
    save_user_phone,
    validate_contact,
)
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


# ==============================================================
# FSM States
# ==============================================================

class ClientBooking(StatesGroup):
    """FSM состояния бронирования."""
    service = State()      # Выбор услуги
    day = State()          # Выбор дня
    time = State()         # Выбор времени
    specialist = State()   # Выбор специалиста 
    phone = State()        # Запрос телефона (если нет)
    confirm = State()      # Подтверждение


# ==============================================================
# Inline Keyboards
# ==============================================================

def packages_list_inline(
    packages: list[dict],
    page: int,
    lang: str
) -> InlineKeyboardMarkup:
    """Список пакетов для выбора (клиент)."""
    total = len(packages)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = packages[start:end]

    buttons = []

    for pkg in page_items:
        duration = pkg.get("total_duration_min", 0)
        price = pkg.get("package_price", 0) or 0
        price_str = f"{int(price)}₽" if price == int(price) else f"{price:.0f}₽"

        buttons.append([
            InlineKeyboardButton(
                text=f"🛎 {pkg['name']} | {duration} мин | {price_str}",
                callback_data=f"book:pkg:{pkg['id']}"
            )
        ])

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text=t("common:prev", lang), callback_data=f"book:pkg_page:{page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))
        nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="book:noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text=t("common:next", lang), callback_data=f"book:pkg_page:{page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text=t("common:cancel", lang), callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def days_calendar_inline(days: list[dict], page: int, lang: str, days_per_page: int = 7) -> InlineKeyboardMarkup:
    """Календарь доступных дней."""
    available_days = [d for d in days if d.get("has_slots")]
    
    if not available_days:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("client:booking:no_days", lang), callback_data="book:noop")],
            [InlineKeyboardButton(text=t("common:back", lang), callback_data="book:back_service")]
        ])

    total = len(available_days)
    total_pages = max(1, math.ceil(total / days_per_page))
    page = max(0, min(page, total_pages - 1))

    start = page * days_per_page
    end = start + days_per_page
    page_items = available_days[start:end]

    buttons = []
    weekday_names = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}

    row = []
    for day_info in page_items:
        date_str = day_info["date"]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        display = f"{weekday_names[dt.weekday()]} {dt.strftime('%d.%m')}"
        row.append(InlineKeyboardButton(text=display, callback_data=f"book:day:{date_str}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text=t("common:prev", lang), callback_data=f"book:day_page:{page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))
        nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="book:noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text=t("common:next", lang), callback_data=f"book:day_page:{page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text=t("common:back", lang), callback_data="book:back_service")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def time_slots_inline(slots: list[dict], page: int, lang: str, slots_per_page: int = 8) -> InlineKeyboardMarkup:
    """Список доступных времён."""
    if not slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("client:booking:no_slots", lang), callback_data="book:noop")],
            [InlineKeyboardButton(text=t("common:back", lang), callback_data="book:back_day")]
        ])

    total = len(slots)
    total_pages = max(1, math.ceil(total / slots_per_page))
    page = max(0, min(page, total_pages - 1))

    start = page * slots_per_page
    end = start + slots_per_page
    page_items = slots[start:end]

    buttons = []
    row = []
    for slot in page_items:
        time_str = slot["time"]
        # Только время — без специалиста
        row.append(InlineKeyboardButton(text=time_str, callback_data=f"book:time:{time_str}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text=t("common:prev", lang), callback_data=f"book:time_page:{page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))
        nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="book:noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text=t("common:next", lang), callback_data=f"book:time_page:{page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text=t("common:back", lang), callback_data="book:back_day")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def specialists_select_inline(specialists: list[dict], time_str: str, lang: str) -> InlineKeyboardMarkup:
    """Выбор специалиста."""
    buttons = [[InlineKeyboardButton(text=f"👤 {spec['name']}", callback_data=f"book:spec:{time_str}:{spec['id']}")] for spec in specialists]
    buttons.append([InlineKeyboardButton(text=t("common:back", lang), callback_data="book:back_time")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_booking_inline(lang: str) -> InlineKeyboardMarkup:
    """Подтверждение бронирования."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("client:booking:confirm_yes", lang), callback_data="book:confirm_yes")],
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data="book:cancel")]
    ])


# ==============================================================
# Flow Setup
# ==============================================================

def setup(menu_controller, get_user_context):
    """Настройка роутера бронирования."""
    router = Router(name="client_booking")
    mc = menu_controller

    # ==========================================================
    # START
    # ==========================================================

    async def start_booking(message: Message, state: FSMContext, lang: str, user_id: int):
        """Точка входа в booking flow."""
        logger.info(f"[BOOKING] Starting for user_id={user_id}")

        await state.update_data(user_id=user_id, lang=lang)

        all_packages = await api.get_packages()
        packages = [p for p in all_packages if p.get("show_on_booking") and p.get("is_active")]
        if not packages:
            await message.answer(t("client:booking:no_services", lang))
            await state.clear()
            return

        await state.update_data(packages=packages)
        await state.set_state(ClientBooking.service)

        kb = packages_list_inline(packages, page=0, lang=lang)
        await mc.show_inline_readonly(message, t("client:booking:select_service", lang), kb)

    # ==========================================================
    # SERVICE
    # ==========================================================

    @router.callback_query(ClientBooking.service, F.data.startswith("book:pkg_page:"))
    async def handle_package_page(callback: CallbackQuery, state: FSMContext):
        page = int(callback.data.split(":")[-1])
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        kb = packages_list_inline(data.get("packages", []), page, lang)
        await mc.edit_inline(callback.message, t("client:booking:select_service", lang), kb)
        await callback.answer()

    @router.callback_query(ClientBooking.service, F.data.startswith("book:pkg:"))
    async def handle_package_select(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[-1])
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        packages = data.get("packages", [])

        pkg = next((p for p in packages if p["id"] == pkg_id), None)
        if not pkg:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        logger.info(f"[BOOKING] Package: {pkg['name']} (id={pkg_id})")

        await state.update_data(
            service_package_id=pkg_id,
            service_name=pkg["name"],
            service_duration=pkg.get("total_duration_min", 0),
            service_price=pkg.get("package_price", 0) or 0,
        )

        locations = await api.get_locations()
        if not locations:
            await callback.answer(t("client:booking:no_locations", lang), show_alert=True)
            return

        location_id = locations[0]["id"]
        company_id = locations[0].get("company_id")
        await state.update_data(location_id=location_id, company_id=company_id)

        calendar = await api.get_slots_calendar(location_id)
        if not calendar or not calendar.get("days"):
            await callback.answer(t("client:booking:no_calendar", lang), show_alert=True)
            return

        days = calendar["days"]
        await state.update_data(calendar_days=days)
        await state.set_state(ClientBooking.day)

        kb = days_calendar_inline(days, page=0, lang=lang)
        await callback.message.edit_text(text=t("client:booking:select_day", lang), reply_markup=kb)
        await callback.answer()

    # ==========================================================
    # DAY
    # ==========================================================

    @router.callback_query(ClientBooking.day, F.data.startswith("book:day_page:"))
    async def handle_day_page(callback: CallbackQuery, state: FSMContext):
        page = int(callback.data.split(":")[-1])
        data = await state.get_data()
        kb = days_calendar_inline(data.get("calendar_days", []), page, data.get("lang", DEFAULT_LANG))
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()

    @router.callback_query(ClientBooking.day, F.data == "book:back_service")
    async def handle_back_to_service(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        await state.set_state(ClientBooking.service)
        kb = packages_list_inline(data.get("packages", []), 0, lang)
        await callback.message.edit_text(text=t("client:booking:select_service", lang), reply_markup=kb)
        await callback.answer()

    @router.callback_query(ClientBooking.day, F.data.startswith("book:day:"))
    async def handle_day_select(callback: CallbackQuery, state: FSMContext):
        date_str = callback.data.split(":")[-1]
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        
        logger.info(f"[BOOKING] Day: {date_str}")
        await state.update_data(selected_date=date_str)
        
        slots_data = await api.get_slots_day(
            data.get("location_id"),
            date=date_str,
            service_package_id=data.get("service_package_id"),
        )
        if not slots_data:
            await callback.answer(t("client:booking:no_slots", lang), show_alert=True)
            return
        
        slots = slots_data.get("available_times", [])
        await state.update_data(time_slots=slots)
        await state.set_state(ClientBooking.time)
        
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        kb = time_slots_inline(slots, 0, lang)
        await callback.message.edit_text(text=t("client:booking:select_time", lang) % dt.strftime("%d.%m.%Y"), reply_markup=kb)
        await callback.answer()

    # ==========================================================
    # TIME
    # ==========================================================

    @router.callback_query(ClientBooking.time, F.data.startswith("book:time_page:"))
    async def handle_time_page(callback: CallbackQuery, state: FSMContext):
        page = int(callback.data.split(":")[-1])
        data = await state.get_data()
        kb = time_slots_inline(data.get("time_slots", []), page, data.get("lang", DEFAULT_LANG))
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()

    @router.callback_query(ClientBooking.time, F.data == "book:back_day")
    async def handle_back_to_day(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        await state.set_state(ClientBooking.day)
        kb = days_calendar_inline(data.get("calendar_days", []), 0, lang)
        await callback.message.edit_text(text=t("client:booking:select_day", lang), reply_markup=kb)
        await callback.answer()

    @router.callback_query(ClientBooking.time, F.data.startswith("book:time:"))
    async def handle_time_select(callback: CallbackQuery, state: FSMContext):
        """Выбор времени → проверка количества специалистов."""
        time_str = callback.data.replace("book:time:", "")  # "10:15"
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        slots = data.get("time_slots", [])
        
        slot = next((s for s in slots if s["time"] == time_str), None)
        if not slot:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        specialists = slot.get("specialists", [])
        await state.update_data(selected_time=time_str, pending_specialists=specialists)
        
        if len(specialists) == 1:
            # Один специалист — пропускаем выбор
            spec = specialists[0]
            logger.info(f"[BOOKING] Time: {time_str}, specialist: {spec.get('name')} (auto)")
            await state.update_data(specialist_id=spec["id"], specialist_name=spec.get("name", "?"))
            await check_phone_and_confirm(callback, state, lang)
        else:
            # Несколько — показываем экран выбора
            logger.info(f"[BOOKING] Time: {time_str}, specialists: {len(specialists)}")
            await state.set_state(ClientBooking.specialist)
            kb = specialists_select_inline(specialists, time_str, lang)
            await callback.message.edit_text(
                text=t("client:booking:select_specialist", lang) % time_str,
                reply_markup=kb
            )
            await callback.answer()
            
    @router.callback_query(ClientBooking.specialist, F.data.startswith("book:spec:"))
    async def handle_specialist_select(callback: CallbackQuery, state: FSMContext):
        """Выбор специалиста → phone gate → подтверждение."""
        parts = callback.data.split(":")
        time_str = f"{parts[2]}:{parts[3]}"
        spec_id = int(parts[4])
        
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        pending_specs = data.get("pending_specialists", [])
        
        spec = next((s for s in pending_specs if s["id"] == spec_id), None)
        spec_name = spec.get("name", "?") if spec else "?"
        
        logger.info(f"[BOOKING] Specialist: {spec_name}")
        
        await state.update_data(selected_time=time_str, specialist_id=spec_id, specialist_name=spec_name)
        await check_phone_and_confirm(callback, state, lang)

    @router.callback_query(ClientBooking.specialist, F.data == "book:back_time")
    async def handle_back_to_time_from_spec(callback: CallbackQuery, state: FSMContext):
        """Назад к выбору времени из экрана специалиста."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        dt = datetime.strptime(data.get("selected_date", "2026-01-01"), "%Y-%m-%d")
        
        await state.set_state(ClientBooking.time)
        kb = time_slots_inline(data.get("time_slots", []), 0, lang)
        await callback.message.edit_text(
            text=t("client:booking:select_time", lang) % dt.strftime("%d.%m.%Y"),
            reply_markup=kb
        )
        await callback.answer()

    # ==========================================================
    # PHONE GATE (перед подтверждением)
    # ==========================================================

    async def check_phone_and_confirm(callback: CallbackQuery, state: FSMContext, lang: str):
        """Проверяет телефон. Если нет — запрашивает."""
        data = await state.get_data()
        user_id = data.get("user_id")
        
        if await phone_required(user_id):
            logger.info(f"[BOOKING] Phone required for user_id={user_id}")
            await state.set_state(ClientBooking.phone)
            
            try:
                await callback.message.delete()
            except Exception:
                pass
            
            await callback.message.answer(
                t("registration:welcome", lang),
                reply_markup=request_phone_keyboard(lang)
            )
            await callback.answer()
        else:
            await show_confirmation(callback.message, state, lang)
            await callback.answer()

    @router.message(ClientBooking.phone, F.content_type == ContentType.CONTACT)
    async def handle_booking_phone(message: Message, state: FSMContext):
        """Обработка Contact."""
        tg_id = message.from_user.id
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        user_id = data.get("user_id")
        
        logger.info(f"[BOOKING] Contact received: tg_id={tg_id}")
        
        valid, phone = validate_contact(message.contact, tg_id)
        if not valid:
            await message.answer(t("registration:error", lang))
            return
        
        success, error_key = await save_user_phone(user_id, phone)
        if not success:
            await message.answer(t(error_key, lang))
            return
        
        await message.answer(t("registration:complete", lang))
        await show_confirmation(message, state, lang)

    @router.message(ClientBooking.phone)
    async def handle_booking_phone_invalid(message: Message, state: FSMContext):
        """Пользователь отправил не Contact."""
        data = await state.get_data()
        await message.answer(t("registration:share_phone_hint", data.get("lang", DEFAULT_LANG)))

    # ==========================================================
    # CONFIRM
    # ==========================================================

    async def show_confirmation(message: Message, state: FSMContext, lang: str):
        """Показать экран подтверждения."""
        data = await state.get_data()
        
        service_name = data.get("service_name", "?")
        service_duration = data.get("service_duration", 0)
        service_price = data.get("service_price", 0)
        selected_date = data.get("selected_date", "")
        selected_time = data.get("selected_time", "")
        specialist_name = data.get("specialist_name", "?")
        
        dt = datetime.strptime(selected_date, "%Y-%m-%d")
        date_display = dt.strftime("%d.%m.%Y")
        price_str = f"{int(service_price)}₽" if service_price == int(service_price) else f"{service_price:.0f}₽"
        
        text = t("client:booking:confirm_text", lang) % (
            service_name, date_display, selected_time, specialist_name, service_duration, price_str
        )
        
        await state.set_state(ClientBooking.confirm)
        kb = confirm_booking_inline(lang)
        
        # Трекаем inline для удаления при back_to_reply
        confirm_msg = await message.answer(text=text, reply_markup=kb)
        await mc._add_inline_id(message.chat.id, confirm_msg.message_id)

    @router.callback_query(ClientBooking.confirm, F.data == "book:confirm_yes")
    async def handle_confirm(callback: CallbackQuery, state: FSMContext):
        """Создание записи."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)

        datetime_str = f"{data.get('selected_date')}T{data.get('selected_time')}:00"
        duration = data.get("service_duration", 60)
        
        dt_start = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
        dt_end = dt_start + timedelta(minutes=duration)

        logger.info(f"[BOOKING] Creating: user={data.get('user_id')}, datetime={datetime_str}")
    
        booking = await api.create_booking(
            company_id=data.get("company_id"),
            location_id=data.get("location_id"),
            specialist_id=data.get("specialist_id"),
            client_id=data.get("user_id"),
            date_start=datetime_str,
            date_end=dt_end.strftime("%Y-%m-%dT%H:%M:%S"),
            duration_minutes=duration,
            service_package_id=data.get("service_package_id"),
            notes="Telegram booking",
        )

        if not booking:
            await callback.answer(t("client:booking:error", lang), show_alert=True)
            await state.clear()
            from bot.app.keyboards.client import client_main
            await mc.back_to_reply(callback.message, client_main(lang), title=t("client:main:title", lang))
            return
        
        # Успех - короткий alert
        await callback.answer(t("client:booking:success_alert", lang), show_alert=True)
        await state.clear()
        
        # Возврат в главное меню
        from bot.app.keyboards.client import client_main
        await mc.back_to_reply(callback.message, client_main(lang), title=t("client:main:title", lang))

    # ==========================================================
    # CANCEL
    # ==========================================================

    @router.callback_query(F.data == "book:cancel")
    async def handle_cancel(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        await callback.answer(t("client:booking:cancelled", lang), show_alert=True)
        await state.clear()
        from bot.app.keyboards.client import client_main
        await mc.back_to_reply(callback.message, client_main(lang), title=t("client:main:title", lang))

    @router.callback_query(F.data == "book:noop")
    async def handle_noop(callback: CallbackQuery):
        await callback.answer()

    router.start_booking = start_booking
    return router

