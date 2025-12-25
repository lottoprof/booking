"""
bot/app/utils/menucontroller.py

ТРАНСПОРТ — техническая отправка/удаление сообщений.

Не знает о бизнес-логике, ролях, конкретных меню.
Только: отправить клавиатуру, удалить сообщение, работа с Redis.
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
    
    Хранит last_menu_message_id в Redis для персистентности.
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

    async def _clear_previous(self, message: Message) -> None:
        """Удалить предыдущее меню бота."""
        chat_id = message.chat.id
        old_id = await self._get_menu_id(chat_id)
        if old_id:
            await self._safe_delete(message.bot, chat_id, old_id)
            await self._del_menu_id(chat_id)

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    async def show(self, message: Message, kb: ReplyKeyboardMarkup) -> None:
        """
        Показать ReplyKeyboard (Type A).
        
        - Удаляет предыдущее меню
        - Отправляет новое с точкой
        - Сразу удаляет сообщение — клавиатура остаётся
        """
        chat_id = message.chat.id
        bot = message.bot

        # 1. Удалить старое
        await self._clear_previous(message)

        # 2. Отправить новое
        msg = await bot.send_message(chat_id, text=".", reply_markup=kb)

        # 3. Сразу удалить — клавиатура остаётся!
        if await self._safe_delete(bot, chat_id, msg.message_id):
            await self._del_menu_id(chat_id)
        else:
            await self._set_menu_id(chat_id, msg.message_id)

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

        await self._clear_previous(message)

        msg = await message.bot.send_message(chat_id, text=text, reply_markup=kb)
        await self._set_menu_id(chat_id, msg.message_id)

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
        """
        chat_id = message.chat.id
        bot = message.bot

        await self._clear_previous(message)

        if delete_user_msg:
            await self._safe_delete(bot, chat_id, message.message_id)

        await bot.send_message(chat_id, text=text, reply_markup=kb)

    async def back_from_inline(
        self, 
        message: Message, 
        kb: ReplyKeyboardMarkup
    ) -> None:
        """
        Вернуться из Inline в Reply меню.
        
        Вызывается из callback_query.message.
        """
        await self._safe_delete(message.bot, message.chat.id, message.message_id)
        await self.show(message, kb)

