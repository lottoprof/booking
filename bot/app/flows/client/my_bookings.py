# bot/app/flows/client/my_bookings.py
"""
Flow для просмотра записей клиента.
"""

import math
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.api import api

PAGE_SIZE = 5

# Временное хранение контекста (user_id, lang, bookings) по chat_id
_context: dict[int, dict] = {}


def my_bookings_inline(bookings: list[dict], page: int, lang: str) -> InlineKeyboardMarkup:
    """Список записей клиента с пагинацией."""
    if not bookings:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("client:bookings:empty", lang), callback_data="mybk:noop")],
            [InlineKeyboardButton(text=t("common:hide", lang), callback_data="mybk:hide")]
        ])
    
    total = len(bookings)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = bookings[start:end]
    
    buttons = []
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
            nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"mybk:page:{page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="mybk:noop"))
        nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="mybk:noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"mybk:page:{page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="mybk:noop"))
        buttons.append(nav_row)
    
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
        
        # Сохраняем контекст для пагинации
        chat_id = message.chat.id
        _context[chat_id] = {
            "user_id": user_id,
            "lang": lang,
            "bookings": bookings,
        }
        
        title = t("client:bookings:title", lang) % len(bookings)
        kb = my_bookings_inline(bookings, page=0, lang=lang)
        
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
        
        kb = my_bookings_inline(bookings, page, lang)
        await callback.message.edit_reply_markup(reply_markup=kb)
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

