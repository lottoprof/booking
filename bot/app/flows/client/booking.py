# bot/app/flows/client/booking.py
"""
FSM бронирования для клиента.

Flow:
1. Услуга (пагинация если > 5)
2. День (Level 1 из Redis)
3. Время + Специалист (Level 2)
4. Подтверждение → POST /bookings

Phone gate интегрирован в client_reply.py — этот flow
вызывается ПОСЛЕ проверки телефона.
"""

import logging
import math
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


# ==============================================================
# FSM States
# ==============================================================

class ClientBooking(StatesGroup):
    """FSM состояния бронирования."""
    service = State()      # Выбор услуги
    day = State()          # Выбор дня
    time = State()         # Выбор времени + специалиста
    confirm = State()      # Подтверждение


# ==============================================================
# Inline Keyboards
# ==============================================================

def services_list_inline(
    services: list[dict],
    page: int,
    lang: str
) -> InlineKeyboardMarkup:
    """Список услуг для выбора (клиент)."""
    total = len(services)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = services[start:end]

    buttons = []

    for svc in page_items:
        # Формат: 🛎 Название | 60 мин | 2500₽
        duration = svc.get("duration_min", 0)
        price = svc.get("price", 0)
        price_str = f"{int(price)}₽" if price == int(price) else f"{price:.0f}₽"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"🛎 {svc['name']} | {duration} мин | {price_str}",
                callback_data=f"book:svc:{svc['id']}"
            )
        ])

    # Пагинация
    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"book:svc_page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))

        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="book:noop"
        ))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"book:svc_page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))

        buttons.append(nav_row)

    # Отмена
    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="book:cancel"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def days_calendar_inline(
    days: list[dict],
    page: int,
    lang: str,
    days_per_page: int = 7
) -> InlineKeyboardMarkup:
    """
    Календарь доступных дней.
    Показывает только дни с has_slots=True.
    """
    # Фильтруем только доступные
    available_days = [d for d in days if d.get("has_slots")]
    
    if not available_days:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=t("client:booking:no_days", lang),
                callback_data="book:noop"
            )],
            [InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data="book:back_service"
            )]
        ])

    total = len(available_days)
    total_pages = max(1, math.ceil(total / days_per_page))
    page = max(0, min(page, total_pages - 1))

    start = page * days_per_page
    end = start + days_per_page
    page_items = available_days[start:end]

    buttons = []

    # Дни по 2 в ряд
    row = []
    for day_info in page_items:
        date_str = day_info["date"]
        # Парсим дату для отображения
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        # Формат: "Пн 20.01"
        weekday_names = {
            0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"
        }
        display = f"{weekday_names[dt.weekday()]} {dt.strftime('%d.%m')}"
        
        row.append(InlineKeyboardButton(
            text=display,
            callback_data=f"book:day:{date_str}"
        ))
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)

    # Пагинация
    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"book:day_page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))

        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="book:noop"
        ))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"book:day_page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))

        buttons.append(nav_row)

    # Назад
    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="book:back_service"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def time_slots_inline(
    slots: list[dict],
    page: int,
    lang: str,
    slots_per_page: int = 8
) -> InlineKeyboardMarkup:
    """
    Список доступных времён.
    Если у слота один специалист — сразу выбираем.
    Если несколько — показываем выбор после.
    """
    if not slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=t("client:booking:no_slots", lang),
                callback_data="book:noop"
            )],
            [InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data="book:back_day"
            )]
        ])

    total = len(slots)
    total_pages = max(1, math.ceil(total / slots_per_page))
    page = max(0, min(page, total_pages - 1))

    start = page * slots_per_page
    end = start + slots_per_page
    page_items = slots[start:end]

    buttons = []

    # Слоты по 2 в ряд
    row = []
    for slot in page_items:
        time_str = slot["time"]
        specialists = slot.get("specialists", [])
        spec_count = len(specialists)
        
        # Если один спец — показываем его имя
        if spec_count == 1:
            spec_name = specialists[0].get("name", "").split()[0]  # Только имя
            display = f"{time_str} ({spec_name})"
            # Сразу выбираем специалиста
            spec_id = specialists[0]["id"]
            callback = f"book:time:{time_str}:{spec_id}"
        else:
            # Несколько специалистов — выбор потом
            display = f"{time_str} ({spec_count})"
            callback = f"book:time_multi:{time_str}"
        
        row.append(InlineKeyboardButton(text=display, callback_data=callback))
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)

    # Пагинация
    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"book:time_page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))

        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="book:noop"
        ))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"book:time_page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="book:noop"))

        buttons.append(nav_row)

    # Назад
    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="book:back_day"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def specialists_select_inline(
    specialists: list[dict],
    time_str: str,
    lang: str
) -> InlineKeyboardMarkup:
    """Выбор специалиста для слота с несколькими специалистами."""
    buttons = []

    for spec in specialists:
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 {spec['name']}",
                callback_data=f"book:spec:{time_str}:{spec['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="book:back_time"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_booking_inline(lang: str) -> InlineKeyboardMarkup:
    """Подтверждение бронирования."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("client:booking:confirm_yes", lang),
                callback_data="book:confirm_yes"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:cancel", lang),
                callback_data="book:cancel"
            )
        ]
    ])


# ==============================================================
# Flow Setup
# ==============================================================

def setup(menu_controller, get_user_context):
    """
    Настройка роутера бронирования.
    
    Вызывается из client_reply.py после phone gate.
    """
    router = Router(name="client_booking")
    mc = menu_controller

    # ==========================================================
    # START: Выбор услуги
    # ==========================================================

    async def start_booking(message: Message, state: FSMContext, lang: str, user_id: int):
        """
        Точка входа в booking flow.
        Вызывается из client_reply.py → do_book().
        """
        logger.info(f"[BOOKING] Starting booking flow for user_id={user_id}")
        
        # Сохраняем user_id для POST /bookings
        await state.update_data(user_id=user_id, lang=lang)
        
        # Получаем список услуг
        services = await api.get_services()
        
        if not services:
            await message.answer(t("client:booking:no_services", lang))
            await state.clear()
            return
        
        # Сохраняем для пагинации
        await state.update_data(services=services)
        await state.set_state(ClientBooking.service)
        
        # Показываем список (Type B1 — readonly inline)
        kb = services_list_inline(services, page=0, lang=lang)
        await mc.show_inline_readonly(
            message,
            t("client:booking:select_service", lang),
            kb
        )

    # ==========================================================
    # SERVICE: Пагинация и выбор
    # ==========================================================

    @router.callback_query(ClientBooking.service, F.data.startswith("book:svc_page:"))
    async def handle_service_page(callback: CallbackQuery, state: FSMContext):
        """Пагинация услуг."""
        page = int(callback.data.split(":")[-1])
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        services = data.get("services", [])
        
        kb = services_list_inline(services, page=page, lang=lang)
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()

    @router.callback_query(ClientBooking.service, F.data.startswith("book:svc:"))
    async def handle_service_select(callback: CallbackQuery, state: FSMContext):
        """Выбор услуги → переход к выбору дня."""
        service_id = int(callback.data.split(":")[-1])
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        services = data.get("services", [])
        
        # Находим выбранную услугу
        service = next((s for s in services if s["id"] == service_id), None)
        if not service:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        logger.info(f"[BOOKING] Service selected: {service['name']} (id={service_id})")
        
        # Сохраняем
        await state.update_data(
            service_id=service_id,
            service_name=service["name"],
            service_duration=service.get("duration_min", 0),
            service_price=service.get("price", 0)
        )
        
        # Получаем календарь (Level 1)
        # TODO: получить location_id (пока берём первую локацию)
        locations = await api.get_locations()
        if not locations:
            await callback.answer(t("client:booking:no_locations", lang), show_alert=True)
            return
        
        location_id = locations[0]["id"]
        await state.update_data(location_id=location_id)
        
        calendar = await api.get_slots_calendar(location_id)
        if not calendar or not calendar.get("days"):
            await callback.answer(t("client:booking:no_calendar", lang), show_alert=True)
            return
        
        days = calendar["days"]
        await state.update_data(calendar_days=days)
        await state.set_state(ClientBooking.day)
        
        # Показываем календарь
        kb = days_calendar_inline(days, page=0, lang=lang)
        await callback.message.edit_text(
            text=t("client:booking:select_day", lang),
            reply_markup=kb
        )
        await callback.answer()

    # ==========================================================
    # DAY: Пагинация и выбор
    # ==========================================================

    @router.callback_query(ClientBooking.day, F.data.startswith("book:day_page:"))
    async def handle_day_page(callback: CallbackQuery, state: FSMContext):
        """Пагинация дней."""
        page = int(callback.data.split(":")[-1])
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        days = data.get("calendar_days", [])
        
        kb = days_calendar_inline(days, page=page, lang=lang)
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()

    @router.callback_query(ClientBooking.day, F.data == "book:back_service")
    async def handle_back_to_service(callback: CallbackQuery, state: FSMContext):
        """Назад к выбору услуги."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        services = data.get("services", [])
        
        await state.set_state(ClientBooking.service)
        
        kb = services_list_inline(services, page=0, lang=lang)
        await callback.message.edit_text(
            text=t("client:booking:select_service", lang),
            reply_markup=kb
        )
        await callback.answer()

    @router.callback_query(ClientBooking.day, F.data.startswith("book:day:"))
    async def handle_day_select(callback: CallbackQuery, state: FSMContext):
        """Выбор дня → переход к выбору времени."""
        date_str = callback.data.split(":")[-1]  # "2026-01-20"
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        service_id = data.get("service_id")
        location_id = data.get("location_id")
        
        logger.info(f"[BOOKING] Day selected: {date_str}")
        
        await state.update_data(selected_date=date_str)
        
        # Получаем слоты (Level 2)
        slots_data = await api.get_slots_day(location_id, service_id, date_str)
        
        if not slots_data:
            await callback.answer(t("client:booking:no_slots", lang), show_alert=True)
            return
        
        slots = slots_data.get("available_times", [])
        await state.update_data(time_slots=slots)
        await state.set_state(ClientBooking.time)
        
        # Показываем слоты
        kb = time_slots_inline(slots, page=0, lang=lang)
        
        # Форматируем дату для заголовка
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%d.%m.%Y")
        
        await callback.message.edit_text(
            text=t("client:booking:select_time", lang) % date_display,
            reply_markup=kb
        )
        await callback.answer()

    # ==========================================================
    # TIME: Пагинация и выбор
    # ==========================================================

    @router.callback_query(ClientBooking.time, F.data.startswith("book:time_page:"))
    async def handle_time_page(callback: CallbackQuery, state: FSMContext):
        """Пагинация слотов."""
        page = int(callback.data.split(":")[-1])
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        slots = data.get("time_slots", [])
        
        kb = time_slots_inline(slots, page=page, lang=lang)
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()

    @router.callback_query(ClientBooking.time, F.data == "book:back_day")
    async def handle_back_to_day(callback: CallbackQuery, state: FSMContext):
        """Назад к выбору дня."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        days = data.get("calendar_days", [])
        
        await state.set_state(ClientBooking.day)
        
        kb = days_calendar_inline(days, page=0, lang=lang)
        await callback.message.edit_text(
            text=t("client:booking:select_day", lang),
            reply_markup=kb
        )
        await callback.answer()

    @router.callback_query(ClientBooking.time, F.data.startswith("book:time:"))
    async def handle_time_select(callback: CallbackQuery, state: FSMContext):
        """
        Выбор времени (один специалист) → подтверждение.
        Формат: book:time:10:00:5
        """
        parts = callback.data.split(":")
        time_str = f"{parts[2]}:{parts[3]}"  # "10:00"
        spec_id = int(parts[4])
        
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        slots = data.get("time_slots", [])
        
        # Находим специалиста
        slot = next((s for s in slots if s["time"] == time_str), None)
        if not slot:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        spec = next((s for s in slot.get("specialists", []) if s["id"] == spec_id), None)
        spec_name = spec.get("name", "?") if spec else "?"
        
        logger.info(f"[BOOKING] Time selected: {time_str}, specialist: {spec_name} (id={spec_id})")
        
        await state.update_data(
            selected_time=time_str,
            specialist_id=spec_id,
            specialist_name=spec_name
        )
        
        # Переходим к подтверждению
        await show_confirmation(callback.message, state, lang)
        await callback.answer()

    @router.callback_query(ClientBooking.time, F.data.startswith("book:time_multi:"))
    async def handle_time_multi(callback: CallbackQuery, state: FSMContext):
        """
        Выбор времени (несколько специалистов) → выбор специалиста.
        """
        time_str = callback.data.split(":")[-1]
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        slots = data.get("time_slots", [])
        
        slot = next((s for s in slots if s["time"] == time_str), None)
        if not slot:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        specialists = slot.get("specialists", [])
        await state.update_data(selected_time=time_str, pending_specialists=specialists)
        
        kb = specialists_select_inline(specialists, time_str, lang)
        await callback.message.edit_text(
            text=t("client:booking:select_specialist", lang) % time_str,
            reply_markup=kb
        )
        await callback.answer()

    @router.callback_query(ClientBooking.time, F.data.startswith("book:spec:"))
    async def handle_specialist_select(callback: CallbackQuery, state: FSMContext):
        """Выбор специалиста → подтверждение."""
        parts = callback.data.split(":")
        time_str = f"{parts[2]}:{parts[3]}"
        spec_id = int(parts[4])
        
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        pending_specs = data.get("pending_specialists", [])
        
        spec = next((s for s in pending_specs if s["id"] == spec_id), None)
        spec_name = spec.get("name", "?") if spec else "?"
        
        logger.info(f"[BOOKING] Specialist selected: {spec_name} (id={spec_id})")
        
        await state.update_data(
            selected_time=time_str,
            specialist_id=spec_id,
            specialist_name=spec_name
        )
        
        await show_confirmation(callback.message, state, lang)
        await callback.answer()

    @router.callback_query(ClientBooking.time, F.data == "book:back_time")
    async def handle_back_to_time(callback: CallbackQuery, state: FSMContext):
        """Назад к выбору времени (из выбора специалиста)."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        slots = data.get("time_slots", [])
        date_str = data.get("selected_date", "")
        
        kb = time_slots_inline(slots, page=0, lang=lang)
        
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%d.%m.%Y")
        
        await callback.message.edit_text(
            text=t("client:booking:select_time", lang) % date_display,
            reply_markup=kb
        )
        await callback.answer()

    # ==========================================================
    # CONFIRM: Подтверждение и создание
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
        
        # Форматируем дату
        dt = datetime.strptime(selected_date, "%Y-%m-%d")
        date_display = dt.strftime("%d.%m.%Y")
        
        # Форматируем цену
        price_str = f"{int(service_price)}₽" if service_price == int(service_price) else f"{service_price:.0f}₽"
        
        # Текст подтверждения
        text = t("client:booking:confirm_text", lang) % (
            service_name,
            date_display,
            selected_time,
            specialist_name,
            service_duration,
            price_str
        )
        
        await state.set_state(ClientBooking.confirm)
        
        kb = confirm_booking_inline(lang)
        await message.edit_text(text=text, reply_markup=kb)

    @router.callback_query(ClientBooking.confirm, F.data == "book:confirm_yes")
    async def handle_confirm(callback: CallbackQuery, state: FSMContext):
        """Создание записи."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        
        user_id = data.get("user_id")
        location_id = data.get("location_id")
        service_id = data.get("service_id")
        specialist_id = data.get("specialist_id")
        selected_date = data.get("selected_date")
        selected_time = data.get("selected_time")
        
        # Формируем datetime
        datetime_str = f"{selected_date}T{selected_time}:00"
        
        logger.info(f"[BOOKING] Creating booking: user={user_id}, service={service_id}, "
                   f"specialist={specialist_id}, datetime={datetime_str}")
        
        # POST /bookings
        booking = await api.create_booking(
            location_id=location_id,
            service_id=service_id,
            specialist_id=specialist_id,
            client_id=user_id,
            datetime_start=datetime_str
        )
        
        if not booking:
            await callback.message.edit_text(
                text=t("client:booking:error", lang),
                reply_markup=None
            )
            await state.clear()
            await callback.answer()
            return
        
        # Успех!
        service_name = data.get("service_name", "?")
        dt = datetime.strptime(selected_date, "%Y-%m-%d")
        date_display = dt.strftime("%d.%m.%Y")
        
        success_text = t("client:booking:success", lang) % (
            service_name,
            date_display,
            selected_time
        )
        
        await callback.message.edit_text(text=success_text, reply_markup=None)
        await state.clear()
        await callback.answer(t("client:booking:success_alert", lang), show_alert=True)

    # ==========================================================
    # CANCEL: Отмена на любом шаге
    # ==========================================================

    @router.callback_query(F.data == "book:cancel")
    async def handle_cancel(callback: CallbackQuery, state: FSMContext):
        """Отмена бронирования."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        
        await callback.message.edit_text(
            text=t("client:booking:cancelled", lang),
            reply_markup=None
        )
        await state.clear()
        await callback.answer()

    @router.callback_query(F.data == "book:noop")
    async def handle_noop(callback: CallbackQuery):
        """Игнорируем noop."""
        await callback.answer()

    # Экспортируем start_booking для вызова из client_reply
    router.start_booking = start_booking

    return router
