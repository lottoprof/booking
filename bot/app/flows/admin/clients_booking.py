"""
bot/app/flows/admin/clients_booking.py

Запись от имени клиента из карточки клиента.
Callback-based flow (без FSM states).
"""

import logging
import math
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.utils.pagination import build_nav_row
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 5
DAYS_PER_PAGE = 7
SLOTS_PER_PAGE = 8


# ==============================================================
# Helpers
# ==============================================================

def _format_name(user: dict) -> str:
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


def _format_price(price: float, lang: str) -> str:
    currency = t("currency", lang)
    return f"{price:,.0f} {currency}".replace(",", " ")


# ==============================================================
# Keyboards
# ==============================================================

def kb_services_list(services: list, page: int, total: int, user_id: int, lang: str) -> InlineKeyboardMarkup:
    """Список услуг с пагинацией."""
    rows = []
    for svc in services:
        duration = svc.get("duration_min", 0)
        price = svc.get("price", 0)
        price_str = f"{int(price)}{t('currency', lang)}" if price == int(price) else f"{price:.0f}{t('currency', lang)}"
        rows.append([InlineKeyboardButton(
            text=f"🛎 {svc['name']} | {duration} {t('common:min', lang)} | {price_str}",
            callback_data=f"adminbook:svc:{user_id}:{svc['id']}"
        )])

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    nav = build_nav_row(page, total_pages, f"adminbook:svc_page:{user_id}:{{p}}", "adminbook:noop", lang)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"client:view:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_days_calendar(days: list, page: int, user_id: int, lang: str) -> InlineKeyboardMarkup:
    """Календарь доступных дней."""
    available_days = [d for d in days if d.get("has_slots")]

    if not available_days:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("client:booking:no_days", lang), callback_data="adminbook:noop")],
            [InlineKeyboardButton(text=t("common:back", lang), callback_data=f"adminbook:start:{user_id}")]
        ])

    total = len(available_days)
    total_pages = max(1, math.ceil(total / DAYS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start = page * DAYS_PER_PAGE
    end = start + DAYS_PER_PAGE
    page_items = available_days[start:end]

    buttons = []
    weekday_names = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}

    row = []
    for day_info in page_items:
        date_str = day_info["date"]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        display = f"{weekday_names[dt.weekday()]} {dt.strftime('%d.%m')}"
        row.append(InlineKeyboardButton(text=display, callback_data=f"adminbook:day:{user_id}:{date_str}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav = build_nav_row(page, total_pages, f"adminbook:day_page:{user_id}:{{p}}", "adminbook:noop", lang)
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text=t("common:back", lang), callback_data=f"adminbook:start:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_time_slots(slots: list, page: int, user_id: int, lang: str) -> InlineKeyboardMarkup:
    """Список доступных времён."""
    if not slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("client:booking:no_slots", lang), callback_data="adminbook:noop")],
            [InlineKeyboardButton(text=t("common:back", lang), callback_data=f"adminbook:back_day:{user_id}")]
        ])

    total = len(slots)
    total_pages = max(1, math.ceil(total / SLOTS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start = page * SLOTS_PER_PAGE
    end = start + SLOTS_PER_PAGE
    page_items = slots[start:end]

    buttons = []
    row = []
    for slot in page_items:
        time_str = slot["time"]
        row.append(InlineKeyboardButton(text=time_str, callback_data=f"adminbook:time:{user_id}:{time_str}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav = build_nav_row(page, total_pages, f"adminbook:time_page:{user_id}:{{p}}", "adminbook:noop", lang)
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text=t("common:back", lang), callback_data=f"adminbook:back_day:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_specialists_select(specialists: list, user_id: int, time_str: str, lang: str) -> InlineKeyboardMarkup:
    """Выбор специалиста."""
    buttons = []
    for spec in specialists:
        buttons.append([InlineKeyboardButton(
            text=f"👤 {spec['name']}",
            callback_data=f"adminbook:spec:{user_id}:{time_str}:{spec['id']}"
        )])
    buttons.append([InlineKeyboardButton(text=t("common:back", lang), callback_data=f"adminbook:back_time:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_confirm(user_id: int, lang: str) -> InlineKeyboardMarkup:
    """Подтверждение записи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:booking:confirm_create", lang), callback_data=f"adminbook:confirm:{user_id}"),
            InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"client:view:{user_id}"),
        ]
    ])


# ==============================================================
# Setup
# ==============================================================

def setup(menu_controller, api):
    router = Router(name="clients_booking")
    mc = menu_controller

    # ----------------------------------------------------------
    # Callback: начало — список услуг
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:start:"))
    async def start_booking(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])

        user = await api.get_user(user_id)
        if not user:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        services = await api.get_services()
        if not services:
            await callback.answer(t("client:booking:no_services", lang), show_alert=True)
            return

        await state.update_data(
            adminbook_client_id=user_id,
            adminbook_client_name=_format_name(user),
            adminbook_services=services,
            adminbook_svc_page=0,
        )

        client_name = _format_name(user)
        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_service", lang)
        kb = kb_services_list(services[:PAGE_SIZE], 0, len(services), user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: пагинация услуг
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:svc_page:"))
    async def paginate_services(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])

        data = await state.get_data()
        services = data.get("adminbook_services", [])
        client_name = data.get("adminbook_client_name", "")
        await state.update_data(adminbook_svc_page=page)

        start = page * PAGE_SIZE
        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_service", lang)
        kb = kb_services_list(services[start:start+PAGE_SIZE], page, len(services), user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "adminbook:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: выбор услуги — календарь дней
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:svc:"))
    async def select_service(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        service_id = int(parts[3])

        data = await state.get_data()
        services = data.get("adminbook_services", [])
        client_name = data.get("adminbook_client_name", "")

        service = next((s for s in services if s["id"] == service_id), None)
        if not service:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        locations = await api.get_locations()
        if not locations:
            await callback.answer(t("client:booking:no_locations", lang), show_alert=True)
            return

        location_id = locations[0]["id"]
        company_id = locations[0].get("company_id")

        calendar = await api.get_slots_calendar(location_id)
        if not calendar or not calendar.get("days"):
            await callback.answer(t("client:booking:no_calendar", lang), show_alert=True)
            return

        days = calendar["days"]
        await state.update_data(
            adminbook_service_id=service_id,
            adminbook_service_name=service["name"],
            adminbook_service_duration=service.get("duration_min", 0),
            adminbook_service_price=service.get("price", 0),
            adminbook_location_id=location_id,
            adminbook_company_id=company_id,
            adminbook_calendar_days=days,
            adminbook_day_page=0,
        )

        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_day", lang)
        kb = kb_days_calendar(days, 0, user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: пагинация дней
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:day_page:"))
    async def paginate_days(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])

        data = await state.get_data()
        days = data.get("adminbook_calendar_days", [])
        client_name = data.get("adminbook_client_name", "")
        await state.update_data(adminbook_day_page=page)

        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_day", lang)
        kb = kb_days_calendar(days, page, user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: выбор дня — список времён
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:day:"))
    async def select_day(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        date_str = parts[3]

        data = await state.get_data()
        client_name = data.get("adminbook_client_name", "")

        slots_data = await api.get_slots_day(
            data.get("adminbook_location_id"),
            data.get("adminbook_service_id"),
            date_str
        )
        if not slots_data:
            await callback.answer(t("client:booking:no_slots", lang), show_alert=True)
            return

        slots = slots_data.get("available_times", [])
        await state.update_data(
            adminbook_selected_date=date_str,
            adminbook_time_slots=slots,
            adminbook_time_page=0,
        )

        dt = datetime.strptime(date_str, "%Y-%m-%d")
        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_time", lang) % dt.strftime("%d.%m.%Y")
        kb = kb_time_slots(slots, 0, user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: back_day — вернуться к календарю
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:back_day:"))
    async def back_to_day(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])

        data = await state.get_data()
        days = data.get("adminbook_calendar_days", [])
        page = data.get("adminbook_day_page", 0)
        client_name = data.get("adminbook_client_name", "")

        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_day", lang)
        kb = kb_days_calendar(days, page, user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: пагинация времён
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:time_page:"))
    async def paginate_time(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])

        data = await state.get_data()
        slots = data.get("adminbook_time_slots", [])
        selected_date = data.get("adminbook_selected_date", "")
        client_name = data.get("adminbook_client_name", "")
        await state.update_data(adminbook_time_page=page)

        dt = datetime.strptime(selected_date, "%Y-%m-%d")
        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_time", lang) % dt.strftime("%d.%m.%Y")
        kb = kb_time_slots(slots, page, user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: выбор времени — специалист или подтверждение
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:time:"))
    async def select_time(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        time_str = parts[3]

        data = await state.get_data()
        slots = data.get("adminbook_time_slots", [])
        client_name = data.get("adminbook_client_name", "")

        slot = next((s for s in slots if s["time"] == time_str), None)
        if not slot:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        specialists = slot.get("specialists", [])
        await state.update_data(
            adminbook_selected_time=time_str,
            adminbook_pending_specialists=specialists,
        )

        if len(specialists) == 1:
            # Один специалист — пропускаем выбор
            spec = specialists[0]
            await state.update_data(
                adminbook_specialist_id=spec["id"],
                adminbook_specialist_name=spec.get("name", "?"),
            )
            await show_confirmation(callback, state, user_id, lang)
        else:
            # Несколько — выбор специалиста
            text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_specialist", lang) % time_str
            kb = kb_specialists_select(specialists, user_id, time_str, lang)
            await mc.edit_inline(callback.message, text, kb)
            await callback.answer()

    # ----------------------------------------------------------
    # Callback: back_time — вернуться к выбору времени
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:back_time:"))
    async def back_to_time(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])

        data = await state.get_data()
        slots = data.get("adminbook_time_slots", [])
        page = data.get("adminbook_time_page", 0)
        selected_date = data.get("adminbook_selected_date", "")
        client_name = data.get("adminbook_client_name", "")

        dt = datetime.strptime(selected_date, "%Y-%m-%d")
        text = t("admin:booking:title", lang) % client_name + "\n\n" + t("client:booking:select_time", lang) % dt.strftime("%d.%m.%Y")
        kb = kb_time_slots(slots, page, user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: выбор специалиста
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:spec:"))
    async def select_specialist(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        time_str = parts[3]
        spec_id = int(parts[4])

        data = await state.get_data()
        pending_specs = data.get("adminbook_pending_specialists", [])

        spec = next((s for s in pending_specs if s["id"] == spec_id), None)
        spec_name = spec.get("name", "?") if spec else "?"

        await state.update_data(
            adminbook_selected_time=time_str,
            adminbook_specialist_id=spec_id,
            adminbook_specialist_name=spec_name,
        )

        await show_confirmation(callback, state, user_id, lang)

    # ----------------------------------------------------------
    # Confirmation screen
    # ----------------------------------------------------------

    async def show_confirmation(callback: CallbackQuery, state: FSMContext, user_id: int, lang: str):
        """Показать экран подтверждения."""
        data = await state.get_data()

        client_name = data.get("adminbook_client_name", "?")
        service_name = data.get("adminbook_service_name", "?")
        service_duration = data.get("adminbook_service_duration", 0)
        service_price = data.get("adminbook_service_price", 0)
        selected_date = data.get("adminbook_selected_date", "")
        selected_time = data.get("adminbook_selected_time", "")
        specialist_name = data.get("adminbook_specialist_name", "?")

        dt = datetime.strptime(selected_date, "%Y-%m-%d")
        date_display = dt.strftime("%d.%m.%Y")
        price_str = _format_price(service_price, lang)

        lines = [
            t("admin:booking:confirm_title", lang),
            "",
            t("admin:booking:confirm_client", lang) % client_name,
            f"🛎 {service_name}",
            f"📅 {date_display} {t('admin:booking:at', lang)} {selected_time}",
            f"👤 {specialist_name}",
            f"⏱ {service_duration} {t('common:min', lang)}",
            f"💰 {price_str}",
        ]

        kb = kb_confirm(user_id, lang)
        await mc.edit_inline(callback.message, "\n".join(lines), kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: подтверждение создания записи
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("adminbook:confirm:"))
    async def confirm_booking(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])

        data = await state.get_data()

        datetime_str = f"{data.get('adminbook_selected_date')}T{data.get('adminbook_selected_time')}:00"
        duration = data.get("adminbook_service_duration", 60)

        dt_start = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
        dt_end = dt_start + timedelta(minutes=duration)

        logger.info(f"[ADMIN BOOKING] Creating: client={user_id}, admin={callback.from_user.id}, datetime={datetime_str}")

        booking = await api.create_booking(
            company_id=data.get("adminbook_company_id"),
            location_id=data.get("adminbook_location_id"),
            service_id=data.get("adminbook_service_id"),
            specialist_id=data.get("adminbook_specialist_id"),
            client_id=data.get("adminbook_client_id"),
            date_start=datetime_str,
            date_end=dt_end.strftime("%Y-%m-%dT%H:%M:%S"),
            duration_minutes=duration,
            initiated_by_user_id=callback.from_user.id,
            initiated_by_role="admin",
            initiated_by_channel="tg_bot",
        )

        if not booking:
            await callback.answer(t("client:booking:error", lang), show_alert=True)
            return

        await callback.answer(t("admin:booking:success", lang), show_alert=True)

        # Clear admin booking state data
        await state.update_data(
            adminbook_client_id=None,
            adminbook_client_name=None,
            adminbook_services=None,
            adminbook_service_id=None,
            adminbook_service_name=None,
            adminbook_service_duration=None,
            adminbook_service_price=None,
            adminbook_location_id=None,
            adminbook_company_id=None,
            adminbook_calendar_days=None,
            adminbook_selected_date=None,
            adminbook_time_slots=None,
            adminbook_selected_time=None,
            adminbook_pending_specialists=None,
            adminbook_specialist_id=None,
            adminbook_specialist_name=None,
        )

        # Возврат к карточке клиента
        from bot.app.flows.admin.clients_find import (
            _format_balance,
            _format_date,
            _format_name,
            _format_phone,
            _role_name,
            kb_client_card,
        )

        user = await api.get_user(user_id)
        if not user:
            await callback.answer()
            return

        name = _format_name(user)
        stats = await api.get_user_stats(user_id) or {}
        wallet = await api.get_wallet(user_id) or {}
        roles = await api.get_user_roles(user_id)

        role_id = min((r.get("role_id", 4) for r in roles), default=4) if roles else 4

        lines = [
            t("admin:client:card_title", lang, name),
            "",
            _format_phone(user.get("phone"), lang),
            t("admin:client:registered", lang, _format_date(user.get("created_at"))),
            t("admin:client:bookings_count", lang, stats.get("total_bookings", 0)),
            t("admin:client:balance", lang, _format_balance(wallet.get("balance", 0), lang)),
            t("admin:client:role", lang, _role_name(role_id, lang)),
        ]

        await mc.edit_inline(callback.message, "\n".join(lines), kb_client_card(user_id, lang))

    return router
