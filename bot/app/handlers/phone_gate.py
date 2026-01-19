# bot/app/handlers/phone_gate.py
"""
Роутер для PhoneGate FSM.

Подключается ОДИН РАЗ в main.py.
Использует функции из phone_utils.py.

Setup:
    from bot.app.handlers.phone_gate import setup_phone_gate
    dp.include_router(setup_phone_gate(menu, get_user_context))
"""

import logging
from typing import Callable

from aiogram import Router, F
from aiogram.types import Message, ContentType
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.keyboards.client import client_main
from bot.app.utils.phone_utils import (
    PhoneGate,
    validate_contact,
    save_user_phone,
)

logger = logging.getLogger(__name__)


# ==============================================================
# Callback Registry
# ==============================================================

# action → async callback(message, state, lang, user_id, action_data)
_callbacks: dict[str, Callable] = {}


def register_phone_callback(action: str, callback: Callable) -> None:
    """
    Регистрирует callback для действия после получения телефона.
    
    Args:
        action: идентификатор ("book", "bookings", "contact", ...)
        callback: async def(message, state, lang, user_id, action_data)
    """
    _callbacks[action] = callback
    logger.info(f"[PHONE_GATE] Registered callback: {action}")


def get_phone_callback(action: str) -> Callable | None:
    """Возвращает callback по action."""
    return _callbacks.get(action)


# ==============================================================
# Router Setup
# ==============================================================

def setup_phone_gate(menu_controller, get_user_context):
    """
    Создаёт роутер с FSM handler для PhoneGate.
    """
    router = Router(name="phone_gate")
    mc = menu_controller

    @router.message(PhoneGate.waiting, F.content_type == ContentType.CONTACT)
    async def handle_phone_contact(message: Message, state: FSMContext):
        """Обработка Contact в PhoneGate."""
        tg_id = message.from_user.id
        data = await state.get_data()
        
        lang = data.get("lang", DEFAULT_LANG)
        action = data.get("next_action")
        action_data = data.get("action_data", {})
        
        logger.info(f"[PHONE_GATE] Contact: tg_id={tg_id}, action={action}")
        
        # Валидация
        valid, phone = validate_contact(message.contact, tg_id)
        if not valid:
            await message.answer(t("registration:error", lang))
            return
        
        # user_id
        ctx = get_user_context(tg_id)
        if not ctx or not ctx.user_id:
            logger.error(f"[PHONE_GATE] No user context: tg_id={tg_id}")
            await message.answer(t("registration:error", lang))
            await state.clear()
            return
        
        user_id = ctx.user_id
        
        # Сохраняем телефон
        success, error_key = await save_user_phone(user_id, phone)
        if not success:
            await message.answer(t(error_key, lang))
            return
        
        # Очищаем FSM
        await state.clear()
        
        # Уведомление
        await message.answer(t("registration:complete", lang))
        
        # Callback
        callback = get_phone_callback(action)
        if callback:
            logger.info(f"[PHONE_GATE] Calling callback: {action}")
            await callback(message, state, lang, user_id, action_data)
        else:
            logger.warning(f"[PHONE_GATE] No callback for: {action}")
            # Fallback — главное меню
            await mc.show(
                message,
                client_main(lang),
                title=t("client:main:title", lang),
                menu_context="client_main"
            )

    @router.message(PhoneGate.waiting)
    async def handle_phone_invalid(message: Message, state: FSMContext):
        """Пользователь отправил не Contact."""
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        await message.answer(t("registration:share_phone_hint", lang))

    return router

