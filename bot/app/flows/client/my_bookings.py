# bot/app/flows/client/my_bookings.py
"""
Flow для просмотра записей клиента.
"""

import math
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.events.formatters import build_address_text, build_maps_url
from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.utils.api import api

PAGE_SIZE = 5

# Временное хранение контекста (user_id, lang, bookings) по chat_id
_context: dict[int, dict] = {}


def my_bookings_inline(
    bookings: list[dict],
    page: int,
    lang: str,
    maps_url: str = "",
) -> InlineKeyboardMarkup:
    """Список записей клиента с пагинацией."""
    if not bookings:
        rows: list[list[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text=t("client:bookings:empty", lang), callback_data="mybk:noop")],
        ]
        if maps_url:
            rows.append([InlineKeyboardButton(text=t("common:show_on_map", lang), url=maps_url)])
        rows.append([InlineKeyboardButton(text=t("common:hide", lang), callback_data="mybk:hide")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    total = len(bookings)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = bookings[start:end]

    buttons: list[list[InlineKeyboardButton]] = []
    for b in page_items:
        dt = datetime.fromisoformat(b["date_start"].replace("Z", ""))
        date_str = dt.strftime("%d.%m")
        time_str = dt.strftime("%H:%M")

        service_name = b.get("service_name", "?")
        status_emoji = "🕐" if b["status"] == "pending" else "✅"

        text = f"{status_emoji} {date_str} {time_str} — {service_name}"
        buttons.append([InlineKeyboardButton(text=text, callback_data="mybk:noop")])

    # Пагинация
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text=t("common:prev", lang), callback_data=f"mybk:page:{page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="mybk:noop"))
        nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="mybk:noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text=t("common:next", lang), callback_data=f"mybk:page:{page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="mybk:noop"))
        buttons.append(nav_row)

    if maps_url:
        buttons.append([InlineKeyboardButton(text=t("common:show_on_map", lang), url=maps_url)])
    buttons.append([InlineKeyboardButton(text=t("common:hide", lang), callback_data="mybk:hide")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def setup(menu_controller):
    """Настройка роутера."""
    router = Router(name="client_my_bookings")
    mc = menu_controller

    async def show_my_bookings(message: Message, user_id: int, lang: str):
        """Показать записи клиента."""
        bookings = await api.get_user_active_bookings(user_id)
        bookings.sort(key=lambda b: b.get("date_start", ""))

        # Build maps URL from first booking's location
        maps_url = ""
        if bookings:
            location_id = bookings[0].get("location_id")
            if location_id:
                location = await api.get_location(location_id)
                if location:
                    loc_data = {
                        "location_city": location.get("city", ""),
                        "location_street": location.get("street", ""),
                        "location_house": location.get("house", ""),
                    }
                    address = build_address_text(loc_data)
                    if address:
                        maps_url = build_maps_url(address)

        # Сохраняем контекст для пагинации
        chat_id = message.chat.id
        _context[chat_id] = {
            "user_id": user_id,
            "lang": lang,
            "bookings": bookings,
            "maps_url": maps_url,
        }

        title = t("client:bookings:title", lang) % len(bookings)
        kb = my_bookings_inline(bookings, page=0, lang=lang, maps_url=maps_url)

        await mc.show_inline_readonly(message, title, kb)

    @router.callback_query(F.data.startswith("mybk:page:"))
    async def handle_page(callback: CallbackQuery):
        """Пагинация."""
        page = int(callback.data.split(":")[-1])
        chat_id = callback.message.chat.id

        # Берём из сохранённого контекста
        ctx = _context.get(chat_id, {})
        lang = ctx.get("lang", DEFAULT_LANG)
        bookings = ctx.get("bookings", [])
        maps_url = ctx.get("maps_url", "")

        title = t("client:bookings:title", lang) % len(bookings)
        kb = my_bookings_inline(bookings, page, lang, maps_url=maps_url)
        await mc.edit_inline(callback.message, title, kb)
        await callback.answer()

    @router.callback_query(F.data == "mybk:hide")
    async def handle_hide(callback: CallbackQuery):
        """Скрыть сообщение."""
        chat_id = callback.message.chat.id
        _context.pop(chat_id, None)  # Очищаем контекст

        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()

    @router.callback_query(F.data == "mybk:noop")
    async def handle_noop(callback: CallbackQuery):
        await callback.answer()

    router.show_my_bookings = show_my_bookings
    return router
