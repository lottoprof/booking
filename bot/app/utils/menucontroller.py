"""
bot/app/utils/menucontroller.py

UI-контроллер навигации Telegram-бота.

Контракт (tg_kbrd.md):
- В чате ровно ОДИН якорь ReplyKeyboard
- Сообщение пользователя НЕ удаляется в Type A
- ReplyKeyboardRemove ЗАПРЕЩЁН между меню
- Удаляется ТОЛЬКО предыдущий якорь (ДО отправки нового)
"""

import logging
import os

from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class MenuController:
    """
    Транспортный слой для Telegram-клавиатур.
    Хранит last_menu_message_id в Redis.
    """

    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL is not set")
        self.redis = redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------

    def _key(self, chat_id: int) -> str:
        return f"tg:menu:{chat_id}"

    async def _get_menu_id(self, chat_id: int) -> int | None:
        val = await self.redis.get(self._key(chat_id))
        return int(val) if val else None

    async def _set_menu_id(self, chat_id: int, msg_id: int) -> None:
        await self.redis.set(self._key(chat_id), str(msg_id))

    async def _del_menu_id(self, chat_id: int) -> None:
        await self.redis.delete(self._key(chat_id))

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------

    async def _safe_delete(self, bot, chat_id: int, msg_id: int) -> bool:
        """Удалить сообщение, игнорируя ошибки."""
        try:
            await bot.delete_message(chat_id, msg_id)
            return True
        except TelegramBadRequest:
            return False

    async def _delete_previous_menu(self, message: Message) -> None:
        """
        Удалить предыдущий якорь меню.
        Вызывается ДО отправки нового.
        """
        chat_id = message.chat.id
        old_id = await self._get_menu_id(chat_id)
        if old_id:
            await self._safe_delete(message.bot, chat_id, old_id)
            await self._del_menu_id(chat_id)
            logger.debug(f"Deleted previous menu {old_id} in chat {chat_id}")

    # ------------------------------------------------------------------
    # Type A: Reply → Reply (основная навигация)
    # ------------------------------------------------------------------

    async def show(self, message: Message, kb: ReplyKeyboardMarkup) -> None:
        """
        Показать ReplyKeyboard (Type A).
        
        Контракт:
        1. Удалить предыдущий якорь меню (ДО отправки нового)
        2. Отправить новое сообщение с клавиатурой
        3. Сохранить message_id как новый якорь
        4. Сообщение пользователя НЕ удаляется!
        
        Результат: в чате остаётся сообщение бота + клавиатура внизу.
        """
        chat_id = message.chat.id
        bot = message.bot

        # 1. Удалить старый якорь
        await self._delete_previous_menu(message)

        # 2. Отправить новое меню (ZWS — невидимый текст)
        msg = await bot.send_message(
            chat_id=chat_id,
            text="\u200b",  # Zero-Width Space
            reply_markup=kb
        )

        # 3. Сохранить как новый якорь
        await self._set_menu_id(chat_id, msg.message_id)
        logger.debug(f"New menu {msg.message_id} in chat {chat_id}")

    # ------------------------------------------------------------------
    # Type B: Reply → Inline
    # ------------------------------------------------------------------

    async def show_inline(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
        *,
        delete_user_msg: bool = True,
    ) -> None:
        """
        Показать InlineKeyboard (Type B).
        
        - Удаляет reply-меню
        - Опционально удаляет сообщение пользователя
        - Inline-сообщение НЕ становится якорем
        """
        chat_id = message.chat.id
        bot = message.bot

        # Удалить reply-меню
        await self._delete_previous_menu(message)

        # Удалить сообщение пользователя (опционально)
        if delete_user_msg:
            await self._safe_delete(bot, chat_id, message.message_id)

        # Показать inline (не сохраняем как якорь!)
        await bot.send_message(chat_id, text=text, reply_markup=kb)

    # ------------------------------------------------------------------
    # Type C: Reply → Reply с текстом (FSM/wizard)
    # ------------------------------------------------------------------

    async def show_with_text(
        self, 
        message: Message, 
        text: str, 
        kb: ReplyKeyboardMarkup
    ) -> None:
        """
        Показать ReplyKeyboard с текстом (Type C).
        
        Для FSM-сценариев где нужен вопрос/инструкция.
        """
        chat_id = message.chat.id

        await self._delete_previous_menu(message)

        msg = await message.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb
        )
        await self._set_menu_id(chat_id, msg.message_id)

    # ------------------------------------------------------------------
    # Inline → Reply (возврат из inline)
    # ------------------------------------------------------------------

    async def back_from_inline(
        self, 
        message: Message, 
        kb: ReplyKeyboardMarkup
    ) -> None:
        """
        Вернуться из Inline в Reply меню.
        
        Вызывается из callback_query.message.
        """
        # Удалить inline-сообщение
        await self._safe_delete(message.bot, message.chat.id, message.message_id)
        
        # Показать reply-меню
        await self.show(message, kb)
