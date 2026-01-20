# bot/app/flows/client/contact.py

"""
Флоу "Связаться с нами".

1. Клиент нажимает "💬 Связаться с нами"
2. Если нет телефона → запрос через PhoneGate
3. Сохраняем телефон → сразу показываем inline-кнопку чата
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.phone_utils import (
    PhoneGate,
    phone_required,
    show_phone_request,
    save_user_phone,
    validate_contact,
)
from bot.app.keyboards.client import client_main
from bot.app.config import SUPPORT_TG_ID, CHANNEL_URL

logger = logging.getLogger(__name__)


# ============================================================
# Inline keyboard (локальная для этого флоу)
# ============================================================

def _contact_support_inline(support_tg_id: int, channel_url: str | None, lang: str) -> InlineKeyboardMarkup:
    """
    Inline-кнопки: связь с поддержкой + подписка на канал.
    """
    buttons = []
    
    # Кнопка связи с поддержкой
    if support_tg_id:
        buttons.append(
            InlineKeyboardButton(
                text=t("client:main:contact", lang),  # "💬 Связаться с нами"
                url=f"tg://user?id={support_tg_id}"
            )
        )
    
    # Кнопка подписки на канал
    if channel_url:
        buttons.append(
            InlineKeyboardButton(
                text=t("client:contact:subscribe", lang),  # "📢 Подписаться"
                url=channel_url
            )
        )
    
    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])


# ============================================================
# Flow
# ============================================================

class ContactFlow:
    """Флоу связи с поддержкой."""
    
    def __init__(self, menu_controller):
        self.mc = menu_controller
    
    async def start(self, message: Message, state: FSMContext, user_id: int) -> None:
        """
        Начало флоу "Связаться с нами".
        """
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        logger.info(f"[CONTACT] start: tg_id={tg_id}, user_id={user_id}")
        
        # Проверяем что хотя бы один контакт настроен
        if not SUPPORT_TG_ID and not CHANNEL_URL:
            logger.warning("[CONTACT] Neither SUPPORT_TG_ID nor CHANNEL_URL configured")
            # Type A: обновляем якорь с сообщением об ошибке
            await self.mc.show(
                message,
                client_main(lang),
                title=t("common:error", lang),
                menu_context=None
            )
            return
        
        # Проверяем наличие телефона
        if await phone_required(user_id):
            # Телефона нет — запрашиваем (Type A внутри show_phone_request)
            await state.set_state(PhoneGate.waiting)
            await state.update_data(
                user_id=user_id,
                next_action="contact"
            )
            await show_phone_request(self.mc, message, lang)
            logger.info("[CONTACT] Phone required, showing request")
            return
        
        # Телефон есть — Type A: обновляем якорь + показываем inline
        await self.mc.show(
            message,
            client_main(lang),
            title=t("client:main:title", lang),
            menu_context=None
        )
        
        kb = _contact_support_inline(SUPPORT_TG_ID, CHANNEL_URL, lang)
        await self.mc.send_inline_in_flow(
            bot=message.bot,
            chat_id=message.chat.id,
            text=t("client:main:contact", lang),
            kb=kb
        )
        logger.info(f"[CONTACT] Chat button shown, support_tg_id={SUPPORT_TG_ID}")
    
    async def on_phone_received(self, message: Message, state: FSMContext) -> None:
        """
        Обработка полученного контакта.
        """
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        # Валидируем контакт
        valid, phone = validate_contact(message.contact, tg_id)
        if not valid:
            await message.answer(t("registration:share_phone_hint", lang))
            return
        
        # Получаем user_id из state
        data = await state.get_data()
        user_id = data.get("user_id")
        
        if not user_id:
            logger.error("[CONTACT] user_id not found in state")
            await state.clear()
            await message.answer(t("common:error", lang))
            return
        
        # Сохраняем телефон
        success, error_key = await save_user_phone(user_id, phone)
        
        if not success:
            await message.answer(t(error_key or "common:error", lang))
            await state.clear()
            return
        
        # Очищаем FSM
        await state.clear()
        
        # Type A: возвращаем клиентское меню (удаляет user message)
        await self.mc.show(
            message,
            client_main(lang),
            title=t("client:main:title", lang),
            menu_context=None
        )
        
        # Показываем inline кнопку чата (user message уже удалён)
        kb = _contact_support_inline(SUPPORT_TG_ID, CHANNEL_URL, lang)
        await self.mc.send_inline_in_flow(
            bot=message.bot,
            chat_id=message.chat.id,
            text=t("client:main:contact", lang),
            kb=kb
        )
        logger.info(f"[CONTACT] Phone saved, chat button shown")


# ============================================================
# Router setup
# ============================================================

def setup(menu_controller, get_user_role) -> Router:
    """Настройка роутера."""
    
    router = Router(name="client_contact")
    flow = ContactFlow(menu_controller)
    
    # Экспортируем для client_reply
    router.flow = flow
    
    # --- FSM: получен контакт ---
    @router.message(PhoneGate.waiting, F.contact)
    async def on_contact(message: Message, state: FSMContext):
        data = await state.get_data()
        if data.get("next_action") == "contact":
            await flow.on_phone_received(message, state)
    
    # --- FSM: текст вместо контакта (подсказка) ---
    @router.message(PhoneGate.waiting, F.text)
    async def on_text(message: Message, state: FSMContext):
        data = await state.get_data()
        if data.get("next_action") != "contact":
            return
            
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        # Подсказка — нужно нажать кнопку
        await message.answer(t("registration:share_phone_hint", lang))
    
    return router
