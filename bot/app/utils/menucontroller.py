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

    async def show(
        self, 
        message: Message, 
        kb: ReplyKeyboardMarkup,
        title: str = "📋"
    ) -> None:
        """
        Показать ReplyKeyboard (Type A).
        
        Порядок критичен для Android:
        1. Отправить новое меню (клавиатура появляется)
        2. Сохранить якорь
        3. Удалить старый якорь бота
        4. Удалить сообщение пользователя (клавиатура уже есть!)
        """
        chat_id = message.chat.id
        bot = message.bot
        
        old_menu_id = await self._get_menu_id(chat_id)
        user_msg_id = message.message_id

        # 1. Отправить новое меню
        msg = await bot.send_message(
            chat_id=chat_id,
            text=title,
            reply_markup=kb
        )
        
        # 2. Сохранить новый якорь
        await self._set_menu_id(chat_id, msg.message_id)

        # 3. Удалить старый якорь бота
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)

        # 4. Удалить сообщение пользователя (ПОСЛЕ — клавиатура уже активна)
        await self._safe_delete(bot, chat_id, user_msg_id)
        
        logger.debug(f"Menu: {old_menu_id} -> {msg.message_id}, deleted user msg {user_msg_id}")

    # ------------------------------------------------------------------
    # Type B: Reply → Inline
    # ------------------------------------------------------------------

    async def show_inline(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        """
        Показать InlineKeyboard (Type B).
        
        Порядок (как в Type A — send first!):
        1. Отправить inline-сообщение
        2. Удалить старый reply-якорь
        3. Удалить сообщение пользователя
        4. Очистить якорь в Redis (inline не является якорем)
        
        Returns:
            Отправленное inline-сообщение (для edit_message)
        """
        chat_id = message.chat.id
        bot = message.bot
        
        old_menu_id = await self._get_menu_id(chat_id)
        user_msg_id = message.message_id

        # 1. Отправить inline-сообщение
        inline_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb
        )

        # 2. Удалить старый reply-якорь
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)

        # 3. Удалить сообщение пользователя
        await self._safe_delete(bot, chat_id, user_msg_id)

        # 4. Очистить якорь (inline НЕ является якорем)
        await self._del_menu_id(chat_id)
        
        logger.debug(f"Inline: deleted menu {old_menu_id}, user msg {user_msg_id}")
        
        return inline_msg

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

    async def back_to_reply(
        self, 
        callback_message: Message, 
        kb: ReplyKeyboardMarkup,
        title: str = "📋"
    ) -> None:
        """
        Вернуться из Inline в Reply меню.
        
        Вызывается из callback_query.message (это inline-сообщение).
        
        Порядок:
        1. Отправить reply-меню
        2. Сохранить якорь
        3. Удалить inline-сообщение
        """
        chat_id = callback_message.chat.id
        bot = callback_message.bot
        inline_msg_id = callback_message.message_id

        # 1. Отправить reply-меню
        msg = await bot.send_message(
            chat_id=chat_id,
            text=title,
            reply_markup=kb
        )
        
        # 2. Сохранить якорь
        await self._set_menu_id(chat_id, msg.message_id)

        # 3. Удалить inline-сообщение
        await self._safe_delete(bot, chat_id, inline_msg_id)
        
        logger.debug(f"Back to reply: {msg.message_id}, deleted inline {inline_msg_id}")

    # ------------------------------------------------------------------
    # Inline → Inline (пагинация, обновление)
    # ------------------------------------------------------------------

    async def edit_inline(
        self,
        callback_message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> None:
        """
        Обновить inline-сообщение (пагинация, изменение данных).
        
        Вызывается из callback_query.message.
        """
        try:
            await callback_message.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            pass  # Контент не изменился

