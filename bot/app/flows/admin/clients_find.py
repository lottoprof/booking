"""
bot/app/flows/admin/clients_find.py

Поиск клиентов + карточка + деактивация.
"""

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


class ClientSearch(StatesGroup):
    query = State()


# ==============================================================
# Helpers
# ==============================================================

def _format_name(user: dict) -> str:
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


def _format_phone(phone: str | None, lang: str) -> str:
    return t("admin:client:phone", lang, phone) if phone else t("admin:client:no_phone", lang)


def _format_date(date_str: str | None) -> str:
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return date_str[:10] if date_str else "—"


def _format_balance(balance: float, lang: str) -> str:
    currency = t("currency", lang)
    return f"{balance:,.0f} {currency}".replace(",", " ")


def _role_name(role_id: int, lang: str) -> str:
    m = {1: "admin", 2: "manager", 3: "specialist", 4: "client"}
    return t(f"role:{m.get(role_id, 'client')}", lang)


# ==============================================================
# Keyboards
# ==============================================================

def kb_search_input(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data="client:cancel")]
    ])


def kb_search_results(users: list, page: int, total: int, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for u in users:
        name = _format_name(u)
        phone = u.get("phone", "")
        short = f"...{phone[-4:]}" if phone and len(phone) >= 4 else ""
        rows.append([InlineKeyboardButton(
            text=f"👤 {name} {short}",
            callback_data=f"client:view:{u['id']}"
        )])
    
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"client:page:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="client:noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"client:page:{page+1}"))
        rows.append(nav)
    
    rows.append([
        InlineKeyboardButton(text=t("admin:clients:new_search", lang), callback_data="client:search"),
        InlineKeyboardButton(text=t("common:back", lang), callback_data="client:back_menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_client_card(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:client:edit", lang), callback_data=f"cedit:menu:{user_id}"),
            InlineKeyboardButton(text=t("admin:client:deactivate", lang), callback_data=f"client:deact:{user_id}"),
        ],
        [
            InlineKeyboardButton(text=t("admin:client:book", lang), callback_data=f"client:book:{user_id}"),
            InlineKeyboardButton(text=t("admin:client:wallet", lang), callback_data=f"wallet:card:{user_id}"),
        ],
        [InlineKeyboardButton(text=t("admin:client:to_list", lang), callback_data="client:back_list")]
    ])


def kb_deactivate_confirm(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:client:deactivate_confirm", lang), callback_data=f"client:deact_yes:{user_id}"),
            InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"client:view:{user_id}"),
        ]
    ])


# ==============================================================
# Setup
# ==============================================================

def setup(menu_controller, api):
    """
    Args:
        menu_controller: MenuController
        api: ApiClient with ClientsApiMixin
    Returns:
        Router
    """
    router = Router(name="clients_find")
    mc = menu_controller

    # ----------------------------------------------------------
    # Entry point (вызывается из admin_reply)
    # ----------------------------------------------------------
    
    async def start_search(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.set_state(ClientSearch.query)
        await state.update_data(search_results=[], search_page=0)
        
        text = f"{t('admin:clients:search_title', lang)}\n\n{t('admin:clients:search_hint', lang)}"
        await mc.show_inline_input(message, text, kb_search_input(lang))
    
    router.start_search = start_search

    # ----------------------------------------------------------
    # FSM: ввод поискового запроса
    # ----------------------------------------------------------
    
    @router.message(ClientSearch.query)
    async def process_query(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        query = message.text.strip()
        
        try:
            await message.delete()
        except Exception:
            pass
        
        if len(query) < 2:
            err = await message.answer(t("admin:clients:search_min", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return
        
        results = await api.search_users(query)
        await state.update_data(search_query=query, search_results=results, search_page=0)
        await state.set_state(None)
        
        if not results:
            text = t("admin:clients:not_found", lang)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("admin:clients:new_search", lang), callback_data="client:search")],
                [InlineKeyboardButton(text=t("common:back", lang), callback_data="client:back_menu")]
            ])
        else:
            text = t("admin:clients:found", lang, len(results))
            kb = kb_search_results(results[:PAGE_SIZE], 0, len(results), lang)
        
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ----------------------------------------------------------
    # Callbacks: навигация
    # ----------------------------------------------------------
    
    @router.callback_query(F.data == "client:cancel")
    @router.callback_query(F.data == "client:back_menu")
    async def back_to_menu(callback: CallbackQuery, state: FSMContext):
        from bot.app.keyboards.admin import admin_clients
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.back_to_reply(callback.message, admin_clients(lang), 
                               title=t("admin:clients:title", lang), menu_context="clients")
        await callback.answer()

    @router.callback_query(F.data == "client:search")
    async def new_search(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.set_state(ClientSearch.query)
        await state.update_data(search_results=[], search_page=0)
        text = f"{t('admin:clients:search_title', lang)}\n\n{t('admin:clients:search_hint', lang)}"
        await mc.edit_inline_input(callback.message, text, kb_search_input(lang))
        await callback.answer()

    @router.callback_query(F.data.startswith("client:page:"))
    async def paginate(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        page = int(callback.data.split(":")[2])
        data = await state.get_data()
        results = data.get("search_results", [])
        await state.update_data(search_page=page)
        
        start = page * PAGE_SIZE
        text = t("admin:clients:found", lang, len(results))
        kb = kb_search_results(results[start:start+PAGE_SIZE], page, len(results), lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "client:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    @router.callback_query(F.data == "client:back_list")
    async def back_to_list(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        results = data.get("search_results", [])
        page = data.get("search_page", 0)
        
        if not results:
            await new_search(callback, state)
            return
        
        start = page * PAGE_SIZE
        text = t("admin:clients:found", lang, len(results))
        kb = kb_search_results(results[start:start+PAGE_SIZE], page, len(results), lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callbacks: карточка клиента
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("client:view:"))
    async def view_client(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        
        user = await api.get_user(user_id)
        if not user:
            await callback.answer("Не найден", show_alert=True)
            return
        
        await state.update_data(current_client_id=user_id)
        
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
        await callback.answer()

    # ----------------------------------------------------------
    # Callbacks: деактивация
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("client:deact:"))
    async def confirm_deactivate(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        
        user = await api.get_user(user_id)
        if not user:
            await callback.answer("Не найден", show_alert=True)
            return
        
        name = _format_name(user)
        active = await api.get_user_active_bookings(user_id)
        
        lines = [t("admin:client:deactivate_title", lang, name)]
        
        if active:
            lines.append("")
            lines.append(t("admin:client:deactivate_warning", lang, len(active)))
            for b in active[:5]:
                ds = b.get("date_start", "")
                try:
                    dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
                    ds = dt.strftime("%d.%m %H:%M")
                except Exception:
                    ds = ds[:16] if ds else "—"
                svc = await api.get_service(b.get("service_id"))
                svc_name = svc.get("name", "—") if svc else "—"
                lines.append(f"• {ds} — {svc_name}")
            if len(active) > 5:
                lines.append(f"• ...+{len(active)-5}")
            lines.append("")
            lines.append(t("admin:client:deactivate_note", lang))
        
        await mc.edit_inline(callback.message, "\n".join(lines), kb_deactivate_confirm(user_id, lang))
        await callback.answer()

    @router.callback_query(F.data.startswith("client:deact_yes:"))
    async def execute_deactivate(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        
        active = await api.get_user_active_bookings(user_id)
        for b in active:
            await api.cancel_booking(b["id"], reason="Клиент деактивирован")
        
        # DELETE /users/{id} — soft-delete
        await api.delete_user(user_id)
        
        data = await state.get_data()
        results = [u for u in data.get("search_results", []) if u["id"] != user_id]
        await state.update_data(search_results=results)
        
        await callback.answer(t("admin:client:deactivated", lang), show_alert=True)
        await back_to_list(callback, state)

    @router.callback_query(F.data.startswith("client:book:"))
    async def book_for_client(callback: CallbackQuery, state: FSMContext):
        user_id = int(callback.data.split(":")[2])
        await state.update_data(booking_for_client_id=user_id)
        await callback.answer("TODO: Запись от имени клиента", show_alert=True)

    return router

