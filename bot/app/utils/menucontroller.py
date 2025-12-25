"""
bot/app/utils/menucontroller.py

UI-контроллер навигации Telegram-бота.

Контракт v1:
- Один якорь ReplyKeyboard на чат (хранится в Redis)
- Type A (Reply→Reply): user message НЕ удаляем, ZWS обязателен
- Type B (Reply→Inline): user message МОЖНО удалить
- Type C (Reply→Reply): без очистки, для пошаговых сценариев
"""

import logging
import os

from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Технический текст для ReplyKeyboard
# ВАЖНО: это НЕ пустая строка, Telegram её принимает
MENU_PLACEHOLDER = "\u200b"  # Zero-Width Space


class MenuController:
    """
    UI-контроллер навигации Telegram-бота.
    
    Хранит message_id последнего меню в Redis для:
    - персистентности между рестартами
    - корректной очистки чата
    """

    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL is not set")

        self.redis = redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    def _menu_key(self, chat_id: int) -> str:
        return f"tg:last_menu:{chat_id}"

    async def _get_last_menu_id(self, chat_id: int) -> int | None:
        value = await self.redis.get(self._menu_key(chat_id))
        return int(value) if value else None

    async def _set_last_menu_id(self, chat_id: int, message_id: int) -> None:
        await self.redis.set(self._menu_key(chat_id), str(message_id))

    async def _del_last_menu_id(self, chat_id: int) -> None:
        await self.redis.delete(self._menu_key(chat_id))

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------

    async def _safe_delete(self, bot, chat_id: int, message_id: int) -> bool:
        """Безопасное удаление сообщения."""
        try:
            await bot.delete_message(chat_id, message_id)
            logger.debug("UI: deleted message %s in chat %s", message_id, chat_id)
            return True
        except TelegramBadRequest as e:
            logger.debug("UI: cannot delete message %s: %s", message_id, e)
            return False

    async def _clear_user_message(self, message: Message) -> None:
        """Удаление сообщения пользователя."""
        await self._safe_delete(message.bot, message.chat.id, message.message_id)

    async def _clear_bot_menu(self, message: Message) -> None:
        """Удаление предыдущего меню бота (якоря ReplyKeyboard)."""
        chat_id = message.chat.id
        menu_id = await self._get_last_menu_id(chat_id)

        if menu_id:
            await self._safe_delete(message.bot, chat_id, menu_id)
            await self._del_last_menu_id(chat_id)

    # ------------------------------------------------------------------
    # TYPE A — Reply → Reply (основная навигация)
    # ------------------------------------------------------------------

    async def navigate(self, message: Message, kb: ReplyKeyboardMarkup) -> None:
        """
        Type A — Reply → Reply
        
        - сообщение пользователя НЕ удаляется (Telegram UX)
        - удаляется ТОЛЬКО предыдущее меню бота
        - новое меню = ZWS + ReplyKeyboard
        
        Args:
            message: входящее сообщение пользователя
            kb: ReplyKeyboardMarkup для показа
        """
        chat_id = message.chat.id
        bot = message.bot

        # 1. Удалить предыдущий якорь
        await self._clear_bot_menu(message)

        # 2. Отправить новое меню
        # КРИТИЧНО: text должен быть непустым!
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=MENU_PLACEHOLDER,  # "\u200b" - не пустая строка
                reply_markup=kb,
            )
        except TelegramBadRequest as e:
            # Fallback: если ZWS не работает, используем точку
            logger.warning("UI: ZWS failed, using fallback: %s", e)
            msg = await bot.send_message(
                chat_id=chat_id,
                text=".",
                reply_markup=kb,
            )

        # 3. Сохранить якорь
        await self._set_last_menu_id(chat_id, msg.message_id)
        logger.debug("UI: menu saved, msg_id=%s, chat=%s", msg.message_id, chat_id)

    # ------------------------------------------------------------------
    # TYPE B — Reply → Inline (вход в inline-сценарий)
    # ------------------------------------------------------------------

    async def finish_to_inline(
        self,
        message: Message,
        text: str,
        inline_kb: InlineKeyboardMarkup,
        *,
        clear_user: bool = True,
    ) -> None:
        """
        Type B — Reply → Inline
        
        - опционально удаляет сообщение пользователя
        - удаляет reply-меню
        - показывает inline-сообщение
        
        Args:
            message: входящее сообщение
            text: текст inline-сообщения (ОБЯЗАТЕЛЬНО непустой!)
            inline_kb: InlineKeyboardMarkup
            clear_user: удалять ли сообщение пользователя
        """
        if not text or not text.strip():
            raise ValueError("text must be non-empty for inline message")

        if clear_user:
            await self._clear_user_message(message)

        await self._clear_bot_menu(message)

        await message.answer(text, reply_markup=inline_kb)
        logger.debug("UI: inline mode, chat=%s", message.chat.id)

    # ------------------------------------------------------------------
    # TYPE C — Reply → Reply без очистки
    # ------------------------------------------------------------------

    async def show_without_clear(
        self, 
        message: Message, 
        text: str, 
        kb: ReplyKeyboardMarkup
    ) -> None:
        """
        Type C — Reply → Reply без очистки
        
        Для пошаговых сценариев (FSM).
        НЕ использовать для навигации меню!
        
        Args:
            message: входящее сообщение
            text: текст сообщения (непустой!)
            kb: ReplyKeyboardMarkup
        """
        if not text or not text.strip():
            text = MENU_PLACEHOLDER

        msg = await message.answer(text, reply_markup=kb)
        await self._set_last_menu_id(message.chat.id, msg.message_id)

    # ------------------------------------------------------------------
    # Inline helpers
    # ------------------------------------------------------------------

    async def show_inline(
        self, 
        message: Message, 
        text: str, 
        inline_kb: InlineKeyboardMarkup
    ) -> None:
        """Показ inline-сообщения (не трогает ReplyKeyboard)."""
        if not text or not text.strip():
            raise ValueError("text must be non-empty")
        await message.answer(text, reply_markup=inline_kb)

    async def update_inline(
        self, 
        message: Message, 
        text: str, 
        inline_kb: InlineKeyboardMarkup
    ) -> None:
        """Обновление inline-сообщения (для callback_query.message)."""
        if not text or not text.strip():
            raise ValueError("text must be non-empty")
        try:
            await message.edit_text(text, reply_markup=inline_kb)
        except TelegramBadRequest as e:
            logger.debug("UI: cannot edit inline: %s", e)

    async def inline_finish_to_menu(
        self, 
        message: Message, 
        kb: ReplyKeyboardMarkup
    ) -> None:
        """
        Inline → Reply (возврат из inline в меню)
        
        - удаляет inline-сообщение
        - показывает ReplyKeyboard
        """
        await self._safe_delete(message.bot, message.chat.id, message.message_id)
        await self.navigate(message, kb)

