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
import json

from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class MenuController:
    """
    Транспортный слой для Telegram-клавиатур.
    Хранит last_menu_message_id в Redis.
    Отслеживает inline-сообщения для очистки.
    """

    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL is not set")
        self.redis = redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Redis keys
    # ------------------------------------------------------------------

    def _menu_key(self, chat_id: int) -> str:
        return f"tg:menu:{chat_id}"

    def _inline_key(self, chat_id: int) -> str:
        return f"tg:inline:{chat_id}"

    # ------------------------------------------------------------------
    # Redis: menu anchor
    # ------------------------------------------------------------------

    async def _get_menu_id(self, chat_id: int) -> int | None:
        val = await self.redis.get(self._menu_key(chat_id))
        return int(val) if val else None

    async def _set_menu_id(self, chat_id: int, msg_id: int) -> None:
        await self.redis.set(self._menu_key(chat_id), str(msg_id))

    async def _del_menu_id(self, chat_id: int) -> None:
        await self.redis.delete(self._menu_key(chat_id))

    # ------------------------------------------------------------------
    # Redis: inline messages tracking
    # ------------------------------------------------------------------

    async def _add_inline_id(self, chat_id: int, msg_id: int) -> None:
        """Добавить inline message в список для очистки."""
        await self.redis.rpush(self._inline_key(chat_id), str(msg_id))

    async def _get_inline_ids(self, chat_id: int) -> list[int]:
        """Получить все tracked inline messages."""
        vals = await self.redis.lrange(self._inline_key(chat_id), 0, -1)
        return [int(v) for v in vals] if vals else []

    async def _clear_inline_ids(self, chat_id: int) -> None:
        """Очистить список inline messages."""
        await self.redis.delete(self._inline_key(chat_id))

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
        """Удалить предыдущий якорь меню."""
        chat_id = message.chat.id
        old_id = await self._get_menu_id(chat_id)
        if old_id:
            await self._safe_delete(message.bot, chat_id, old_id)
            await self._del_menu_id(chat_id)

    async def _delete_all_inline(self, bot, chat_id: int) -> int:
        """Удалить все tracked inline сообщения. Возвращает кол-во удалённых."""
        inline_ids = await self._get_inline_ids(chat_id)
        deleted = 0
        for msg_id in inline_ids:
            if await self._safe_delete(bot, chat_id, msg_id):
                deleted += 1
        await self._clear_inline_ids(chat_id)
        return deleted

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

        # 4. Удалить сообщение пользователя
        await self._safe_delete(bot, chat_id, user_msg_id)

    # Alias для совместимости
    async def navigate(self, message: Message, kb: ReplyKeyboardMarkup) -> None:
        await self.show(message, kb)

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
        Трекает inline message для последующей очистки.
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

        # 2. Трекаем inline для очистки
        await self._add_inline_id(chat_id, inline_msg.message_id)

        # 3. Удалить старый reply-якорь
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)

        # 4. Удалить сообщение пользователя
        await self._safe_delete(bot, chat_id, user_msg_id)

        # 5. Очистить якорь (inline НЕ является якорем)
        await self._del_menu_id(chat_id)
        
        return inline_msg

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
        Удаляет ВСЕ tracked inline-сообщения.
        """
        chat_id = callback_message.chat.id
        bot = callback_message.bot

        # 1. Отправить reply-меню
        msg = await bot.send_message(
            chat_id=chat_id,
            text=title,
            reply_markup=kb
        )
        
        # 2. Сохранить якорь
        await self._set_menu_id(chat_id, msg.message_id)

        # 3. Удалить ВСЕ tracked inline-сообщения
        deleted = await self._delete_all_inline(bot, chat_id)
        logger.debug(f"Back to reply: deleted {deleted} inline messages")

    # ------------------------------------------------------------------
    # Inline → Inline (пагинация, обновление)
    # ------------------------------------------------------------------

    async def edit_inline(
        self,
        callback_message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> None:
        """Обновить inline-сообщение."""
        try:
            await callback_message.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            pass

    # ------------------------------------------------------------------
    # FSM: новое inline в процессе flow
    # ------------------------------------------------------------------

    async def send_inline_in_flow(
        self,
        bot,
        chat_id: int,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        """
        Отправить новое inline-сообщение в процессе FSM.
        Трекает для последующей очистки.
        Не удаляет предыдущие сообщения.
        """
        inline_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb
        )
        await self._add_inline_id(chat_id, inline_msg.message_id)
        return inline_msg

