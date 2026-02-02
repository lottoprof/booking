"""
bot/app/flows/admin/clients_bookings_list.py

Список активных записей (pending/confirmed).
"""

import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang

PAGE_SIZE = 5


def _format_name(user: dict) -> str:
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


def kb_bookings_list(bookings: list, page: int, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура списка записей с пагинацией."""
    rows = []
    total_pages = max(1, math.ceil(len(bookings) / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    page_bookings = bookings[start:start + PAGE_SIZE]

    for b in page_bookings:
        service_name = b.get("_service_name", "?")
        client_name = b.get("_client_name", "?")
        client_id = b.get("client_id")
        rows.append([InlineKeyboardButton(
            text=f"{service_name} — {client_name}",
            callback_data=f"client:view:{client_id}"
        )])

    # Навигация
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"clbook:page:{page-1}"))
        else:
            nav.append(InlineKeyboardButton(text=" ", callback_data="clbook:noop"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="clbook:noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"clbook:page:{page+1}"))
        else:
            nav.append(InlineKeyboardButton(text=" ", callback_data="clbook:noop"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("common:back", lang), callback_data="clbook:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def setup(menu_controller, api):
    router = Router(name="clients_bookings_list")
    mc = menu_controller

    async def show_bookings_list(message: Message):
        """Entry point — показать список активных записей."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        # Получаем активные записи (pending + confirmed)
        bookings = await api.get_bookings(status="pending")
        bookings += await api.get_bookings(status="confirmed")

        if not bookings:
            text = t("admin:bookings_list:empty", lang)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("common:back", lang), callback_data="clbook:back")]
            ])
            await mc.show_inline_readonly(message, text, kb)
            return

        # Собираем данные для отображения
        services = await api.get_services()
        service_map = {s["id"]: s["name"] for s in services}

        users_cache = {}
        for b in bookings:
            b["_service_name"] = service_map.get(b["service_id"], "?")
            client_id = b["client_id"]
            if client_id not in users_cache:
                user = await api.get_user(client_id)
                users_cache[client_id] = _format_name(user) if user else "?"
            b["_client_name"] = users_cache[client_id]

        # Сортировка по дате (ближайшие первыми)
        bookings.sort(key=lambda x: x.get("date_start", ""))

        # Сохраняем в кэш роутера
        router._bookings_cache[message.chat.id] = bookings

        text = t("admin:bookings_list:title", lang) % len(bookings)
        kb = kb_bookings_list(bookings, 0, lang)
        await mc.show_inline_readonly(message, text, kb)

    router.show_bookings_list = show_bookings_list
    router._bookings_cache = {}

    @router.callback_query(F.data.startswith("clbook:page:"))
    async def handle_page(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        page = int(callback.data.split(":")[2])
        bookings = router._bookings_cache.get(callback.message.chat.id, [])

        if not bookings:
            await callback.answer()
            return

        text = t("admin:bookings_list:title", lang) % len(bookings)
        kb = kb_bookings_list(bookings, page, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "clbook:noop")
    async def handle_noop(callback: CallbackQuery):
        await callback.answer()

    @router.callback_query(F.data == "clbook:back")
    async def back_to_menu(callback: CallbackQuery):
        from bot.app.keyboards.admin import admin_clients
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await mc.back_to_reply(
            callback.message,
            admin_clients(lang),
            title=t("admin:clients:title", lang),
            menu_context="clients"
        )
        await callback.answer()

    return router
