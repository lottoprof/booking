"""
bot/app/flows/admin/schedule_bookings.py

Просмотр активных записей на ближайшую неделю.
"""

import logging
from datetime import datetime, date, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


# ==============================================================
# Helpers
# ==============================================================

def _format_date(date_str: str) -> str:
    """Форматирует дату в dd.mm."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m")
    except Exception:
        return date_str[:10] if date_str else "—"


def _format_time(date_str: str) -> str:
    """Форматирует время в HH:MM."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except Exception:
        return "—"


def _format_name(user: dict) -> str:
    """Форматирует имя пользователя."""
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


def _status_text(status: str, lang: str) -> str:
    """Возвращает текст статуса."""
    key_map = {
        "pending": "admin:schbook:status_pending",
        "confirmed": "admin:schbook:status_confirmed",
    }
    key = key_map.get(status, "admin:schbook:status_pending")
    return t(key, lang)


# ==============================================================
# Keyboards
# ==============================================================

def kb_bookings_list(
    bookings: list[dict],
    page: int,
    total: int,
    lang: str,
) -> InlineKeyboardMarkup:
    """Клавиатура со списком записей и пагинацией."""
    rows = []

    for b in bookings:
        date_str = _format_date(b.get("date_start", ""))
        time_str = _format_time(b.get("date_start", ""))
        service_name = b.get("_service_name", "—")
        text = t("admin:schbook:item", lang, date_str, time_str, service_name)
        rows.append([InlineKeyboardButton(
            text=text,
            callback_data=f"schbook:view:{b['id']}"
        )])

    # Пагинация
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text=t("common:prev", lang),
                callback_data=f"schbook:page:{page - 1}"
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="schbook:noop"
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text=t("common:next", lang),
                callback_data=f"schbook:page:{page + 1}"
            ))
        rows.append(nav)

    # Кнопка очистки
    rows.append([InlineKeyboardButton(
        text=t("admin:schbook:clear", lang),
        callback_data="schbook:clear"
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_booking_detail(booking_id: int, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура карточки записи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="schbook:back_list"
        )]
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
    router = Router(name="schedule_bookings")
    mc = menu_controller

    # ----------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------

    async def show_bookings(message: Message):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        today = date.today()
        date_from = today.isoformat()
        date_to = (today + timedelta(days=7)).isoformat()

        # Получаем записи со статусами pending и confirmed
        pending = await api.get_bookings(
            date_from=date_from,
            date_to=date_to,
            status="pending"
        )
        confirmed = await api.get_bookings(
            date_from=date_from,
            date_to=date_to,
            status="confirmed"
        )
        all_bookings = pending + confirmed

        # Сортируем по дате
        all_bookings.sort(key=lambda b: b.get("date_start", ""))

        # Добавляем названия услуг
        services_cache = {}
        for b in all_bookings:
            svc_id = b.get("service_id")
            if svc_id not in services_cache:
                svc = await api.get_service(svc_id)
                services_cache[svc_id] = svc.get("name", "—") if svc else "—"
            b["_service_name"] = services_cache[svc_id]

        if not all_bookings:
            text = t("admin:schbook:empty", lang)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=t("admin:schbook:clear", lang),
                    callback_data="schbook:clear"
                )]
            ])
        else:
            text = t("admin:schbook:title", lang)
            kb = kb_bookings_list(all_bookings[:PAGE_SIZE], 0, len(all_bookings), lang)

        # Сохраняем в FSM для пагинации
        # Храним данные в Redis через FSMContext - нужно получить state
        # Так как это entry point из Reply кнопки, храним локально
        router._bookings_cache = {
            message.chat.id: {
                "bookings": all_bookings,
                "page": 0,
            }
        }

        await mc.show_inline_readonly(message, text, kb)

    router.show_bookings = show_bookings

    # ----------------------------------------------------------
    # Callbacks
    # ----------------------------------------------------------

    @router.callback_query(F.data == "schbook:clear")
    async def clear_screen(callback: CallbackQuery):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()

    @router.callback_query(F.data == "schbook:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    @router.callback_query(F.data.startswith("schbook:page:"))
    async def paginate(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        page = int(callback.data.split(":")[2])

        cache = getattr(router, "_bookings_cache", {}).get(callback.message.chat.id, {})
        bookings = cache.get("bookings", [])

        if not bookings:
            await callback.answer()
            return

        router._bookings_cache[callback.message.chat.id]["page"] = page

        start = page * PAGE_SIZE
        text = t("admin:schbook:title", lang)
        kb = kb_bookings_list(bookings[start:start + PAGE_SIZE], page, len(bookings), lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("schbook:view:"))
    async def view_booking(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        booking_id = int(callback.data.split(":")[2])

        booking = await api.get_booking(booking_id)
        if not booking:
            await callback.answer(t("common:not_found", lang), show_alert=True)
            return

        # Получаем связанные данные
        client = await api.get_user(booking.get("client_id"))
        service = await api.get_service(booking.get("service_id"))
        specialist = await api.get_specialist(booking.get("specialist_id"))

        client_name = _format_name(client) if client else "—"
        service_name = service.get("name", "—") if service else "—"

        spec_name = "—"
        if specialist:
            spec_user = await api.get_user(specialist.get("user_id"))
            spec_name = specialist.get("display_name") or (_format_name(spec_user) if spec_user else "—")

        date_str = _format_date(booking.get("date_start", ""))
        time_str = _format_time(booking.get("date_start", ""))
        status_str = _status_text(booking.get("status", "pending"), lang)

        lines = [
            t("admin:schbook:detail_title", lang, booking_id),
            "",
            t("admin:schbook:client", lang, client_name),
            t("admin:schbook:service", lang, service_name),
            t("admin:schbook:specialist", lang, spec_name),
            t("admin:schbook:datetime", lang, date_str, time_str),
            t("admin:schbook:status", lang, status_str),
        ]

        await mc.edit_inline(callback.message, "\n".join(lines), kb_booking_detail(booking_id, lang))
        await callback.answer()

    @router.callback_query(F.data == "schbook:back_list")
    async def back_to_list(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        cache = getattr(router, "_bookings_cache", {}).get(callback.message.chat.id, {})
        bookings = cache.get("bookings", [])
        page = cache.get("page", 0)

        if not bookings:
            text = t("admin:schbook:empty", lang)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=t("admin:schbook:clear", lang),
                    callback_data="schbook:clear"
                )]
            ])
        else:
            text = t("admin:schbook:title", lang)
            start = page * PAGE_SIZE
            kb = kb_bookings_list(bookings[start:start + PAGE_SIZE], page, len(bookings), lang)

        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    return router
