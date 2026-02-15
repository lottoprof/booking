"""
bot/app/flows/admin/clients_edit.py

Редактирование клиента: имя, фамилия, телефон, роль.
"""

import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)


class ClientEdit(StatesGroup):
    first_name = State()
    last_name = State()
    phone = State()


# ==============================================================
# Helpers
# ==============================================================

def _format_name(user: dict) -> str:
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


def validate_phone(phone: str) -> str | None:
    """Нормализует телефон. Возвращает +7XXXXXXXXXX или None."""
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    if digits.startswith('7') and len(digits) == 11:
        return '+' + digits
    if len(digits) == 10:
        return '+7' + digits
    return None


# ==============================================================
# Keyboards
# ==============================================================

def kb_edit_menu(user: dict, lang: str) -> InlineKeyboardMarkup:
    user_id = user["id"]
    first = user.get("first_name", "—")
    last = user.get("last_name", "—")
    phone = user.get("phone", "—")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{t('admin:client:edit_first_name', lang)}: {first}",
            callback_data=f"cedit:first:{user_id}"
        )],
        [InlineKeyboardButton(
            text=f"{t('admin:client:edit_last_name', lang)}: {last}",
            callback_data=f"cedit:last:{user_id}"
        )],
        [InlineKeyboardButton(
            text=f"{t('admin:client:edit_phone', lang)}: {phone or '—'}",
            callback_data=f"cedit:phone:{user_id}"
        )],
        [InlineKeyboardButton(
            text=t("admin:client:edit_role", lang),
            callback_data=f"cedit:role:{user_id}"
        )],
        [InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data=f"client:view:{user_id}"
        )]
    ])


def kb_role_select(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("role:client", lang), callback_data=f"cedit:setrole:{user_id}:client")],
        [InlineKeyboardButton(text=t("role:specialist", lang), callback_data=f"cedit:setrole:{user_id}:specialist")],
        [InlineKeyboardButton(text=t("role:manager", lang), callback_data=f"cedit:setrole:{user_id}:manager")],
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"cedit:menu:{user_id}")]
    ])


def kb_cancel(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"cedit:menu:{user_id}")]
    ])


# ==============================================================
# Setup
# ==============================================================

def setup(menu_controller, api):
    router = Router(name="clients_edit")
    mc = menu_controller

    # ----------------------------------------------------------
    # show_edit_menu - экспортируется для вызова из clients_find
    # ----------------------------------------------------------
    
    async def show_edit_menu(callback: CallbackQuery, state: FSMContext, user_id: int):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user = await api.get_user(user_id)
        if not user:
            await callback.answer("Не найден", show_alert=True)
            return
        
        await state.update_data(edit_user_id=user_id)
        name = _format_name(user)
        text = t("admin:client:edit_title", lang, name)
        await mc.edit_inline(callback.message, text, kb_edit_menu(user, lang))
        await callback.answer()
    
    router.show_edit_menu = show_edit_menu

    # ----------------------------------------------------------
    # Callback: меню редактирования
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("cedit:menu:"))
    async def edit_menu(callback: CallbackQuery, state: FSMContext):
        user_id = int(callback.data.split(":")[2])
        await state.set_state(None)
        await show_edit_menu(callback, state, user_id)

    # ----------------------------------------------------------
    # Callback: выбор поля для редактирования
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("cedit:first:"))
    async def edit_first_name(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        await state.set_state(ClientEdit.first_name)
        await state.update_data(edit_user_id=user_id)
        text = t("admin:client:enter_first_name", lang)
        await mc.edit_inline_input(callback.message, text, kb_cancel(user_id, lang))
        await callback.answer()

    @router.callback_query(F.data.startswith("cedit:last:"))
    async def edit_last_name(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        await state.set_state(ClientEdit.last_name)
        await state.update_data(edit_user_id=user_id)
        text = t("admin:client:enter_last_name", lang)
        await mc.edit_inline_input(callback.message, text, kb_cancel(user_id, lang))
        await callback.answer()

    @router.callback_query(F.data.startswith("cedit:phone:"))
    async def edit_phone(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        await state.set_state(ClientEdit.phone)
        await state.update_data(edit_user_id=user_id)
        text = t("admin:client:enter_phone", lang)
        await mc.edit_inline_input(callback.message, text, kb_cancel(user_id, lang))
        await callback.answer()

    @router.callback_query(F.data.startswith("cedit:role:"))
    async def edit_role(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        text = t("admin:client:select_role", lang)
        await mc.edit_inline(callback.message, text, kb_role_select(user_id, lang))
        await callback.answer()

    # ----------------------------------------------------------
    # FSM: обработка ввода
    # ----------------------------------------------------------
    
    @router.message(ClientEdit.first_name)
    async def save_first_name(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        value = message.text.strip()
        
        try:
            await message.delete()
        except Exception:
            pass
        
        if len(value) < 2:
            err = await message.answer(t("admin:client:error_name", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return
        
        data = await state.get_data()
        user_id = data.get("edit_user_id")
        await api.update_user(user_id, first_name=value)
        
        await state.set_state(None)
        user = await api.get_user(user_id)
        name = _format_name(user)
        
        text = f"{t('admin:client:saved', lang)}\n\n{t('admin:client:edit_title', lang, name)}"
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb_edit_menu(user, lang))

    @router.message(ClientEdit.last_name)
    async def save_last_name(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        value = message.text.strip()
        
        try:
            await message.delete()
        except Exception:
            pass
        
        if len(value) < 2:
            err = await message.answer(t("admin:client:error_name", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return
        
        data = await state.get_data()
        user_id = data.get("edit_user_id")
        await api.update_user(user_id, last_name=value)
        
        await state.set_state(None)
        user = await api.get_user(user_id)
        name = _format_name(user)
        
        text = f"{t('admin:client:saved', lang)}\n\n{t('admin:client:edit_title', lang, name)}"
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb_edit_menu(user, lang))

    @router.message(ClientEdit.phone)
    async def save_phone(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        value = message.text.strip()
        
        try:
            await message.delete()
        except Exception:
            pass
        
        phone = validate_phone(value)
        if not phone:
            err = await message.answer(t("admin:client:error_phone", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return
        
        data = await state.get_data()
        user_id = data.get("edit_user_id")
        await api.update_user(user_id, phone=phone)
        
        await state.set_state(None)
        user = await api.get_user(user_id)
        name = _format_name(user)
        
        text = f"{t('admin:client:saved', lang)}\n\n{t('admin:client:edit_title', lang, name)}"
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb_edit_menu(user, lang))

    # ----------------------------------------------------------
    # Callback: смена роли
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("cedit:setrole:"))
    async def set_role(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        new_role = parts[3]  # client, specialist, manager
        
        # PATCH /users/{id}/role
        result = await api.change_user_role(user_id, new_role)
        
        if result:
            await callback.answer(t("admin:client:saved", lang))
        else:
            await callback.answer("❌ Ошибка", show_alert=True)
        
        await show_edit_menu(callback, state, user_id)

    return router

