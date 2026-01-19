# bot/app/utils/phone_utils.py
"""
Переиспользуемые функции для запроса и сохранения телефона.

Использование в client_reply.py:
    1. Проверить: if await phone_required(user_id): ...
    2. Установить FSM: await state.set_state(PhoneGate.waiting)
    3. Сохранить next_action: await state.update_data(next_action="book")
    4. Показать: await show_phone_request(mc, message, lang)
    5. Handler Contact в client_reply обрабатывает PhoneGate.waiting
"""

import logging
from typing import Optional

from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup

from bot.app.keyboards.common import request_phone_keyboard
from bot.app.i18n.loader import t
from bot.app.utils.api import api

logger = logging.getLogger(__name__)


# ===============================
# FSM STATE
# ===============================

class PhoneGate(StatesGroup):
    """FSM для запроса телефона перед действием."""
    waiting = State()


# ===============================
# FUNCTIONS
# ===============================

def normalize_phone(phone: str) -> str:
    """Нормализует телефон: добавляет + если нет."""
    if phone and not phone.startswith('+'):
        return '+' + phone
    return phone


async def phone_required(user_id: int) -> bool:
    """
    Проверяет, нужен ли запрос телефона.
    
    Returns:
        True — телефон отсутствует, нужен запрос
        False — телефон уже есть
    """
    user = await api.get_user(user_id)
    if not user:
        logger.warning(f"[PHONE] User not found: {user_id}")
        return True
    
    has_phone = bool(user.get("phone"))
    logger.info(f"[PHONE] user_id={user_id}, has_phone={has_phone}")
    return not has_phone


async def show_phone_request(
    mc,
    message: Message,
    lang: str,
    title_key: str = "registration:welcome"
) -> None:
    """Показывает клавиатуру запроса телефона."""
    await mc.show(
        message,
        request_phone_keyboard(lang),
        title=t(title_key, lang),
        menu_context="phone_request"
    )


async def show_phone_request_for_chat(
    mc,
    bot,
    chat_id: int,
    lang: str,
    title_key: str = "registration:welcome"
) -> None:
    """Показывает клавиатуру запроса телефона (без Message)."""
    await mc.show_for_chat(
        bot=bot,
        chat_id=chat_id,
        kb=request_phone_keyboard(lang),
        title=t(title_key, lang),
        menu_context="phone_request"
    )


async def save_user_phone(user_id: int, phone: str) -> tuple[bool, Optional[str]]:
    """
    Сохраняет телефон пользователя.
    Backend автоматически делает matching с imported_clients.
    
    Returns:
        (True, None) — успех
        (False, error_key) — ошибка
    """
    phone = normalize_phone(phone)
    
    logger.info(f"[PHONE] Saving phone for user_id={user_id}: {phone}")
    
    result = await api.update_user(user_id, phone=phone)
    
    if result:
        logger.info(f"[PHONE] Phone saved successfully")
        return True, None
    else:
        logger.error(f"[PHONE] Failed to save phone")
        return False, "registration:error"


def validate_contact(contact, tg_id: int) -> tuple[bool, Optional[str]]:
    """
    Валидирует полученный контакт.
    
    Returns:
        (True, phone) — валидный контакт
        (False, None) — невалидный
    """
    if contact.user_id != tg_id:
        logger.warning(f"[PHONE] Contact user_id mismatch: {contact.user_id} != {tg_id}")
        return False, None
    
    phone = contact.phone_number
    if not phone:
        logger.warning(f"[PHONE] Contact has no phone number")
        return False, None
    
    return True, normalize_phone(phone)

