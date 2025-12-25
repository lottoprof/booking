"""
bot/app/utils/menucontroller.py

UI-контроллер навигации Telegram-бота.

Контракт:
- Type A (Reply→Reply): чистая смена клавиатуры без мусора в чате
- Type B (Reply→Inline): переход к inline-взаимодействию
- Type C (Reply→Reply): пошаговые сценарии с текстом

Ключевой трюк: отправляем сообщение с клавиатурой, затем СРАЗУ удаляем.
Клавиатура остаётся, сообщение исчезает.
"""

import logging
import os

from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class MenuController:
    """UI-контроллер навигации Telegram-бота."""

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
            return True
        except TelegramBadRequest:
            return False

    async def _clear_prev_menu(self, message: Message) -> None:
        """Удаление предыдущего меню бота из Redis."""
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
        Type A — Reply → Reply (чистая смена клавиатуры)
        
        Алгоритм:
        1. Удаляем предыдущее меню бота (если есть в Redis)
        2. Отправляем новое сообщение с клавиатурой
        3. СРАЗУ удаляем это сообщение — клавиатура ОСТАЁТСЯ!
        4. Сообщение пользователя НЕ трогаем (Telegram UX)
        
        Результат: чистый чат, только клавиатура внизу.
        """
        chat_id = message.chat.id
        bot = message.bot

        # 1. Удалить предыдущий якорь
        await self._clear_prev_menu(message)

        # 2. Отправить сообщение с клавиатурой
        # Telegram требует непустой текст
        msg = await bot.send_message(
            chat_id=chat_id,
            text=".",  # Любой текст, всё равно удалим
            reply_markup=kb,
        )

        # 3. СРАЗУ удаляем сообщение — клавиатура остаётся!
        deleted = await self._safe_delete(bot, chat_id, msg.message_id)
        
        if not deleted:
            # Если не удалось удалить — сохраняем в Redis для будущей очистки
            await self._set_last_menu_id(chat_id, msg.message_id)
            logger.debug("UI: menu msg saved for later cleanup: %s", msg.message_id)
        else:
            # Удалили успешно — очищаем Redis
            await self._del_last_menu_id(chat_id)
            logger.debug("UI: clean menu switch in chat %s", chat_id)

    # ------------------------------------------------------------------
    # TYPE B — Reply → Inline
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
        
        - удаляет reply-меню
        - опционально удаляет сообщение пользователя
        - показывает inline-сообщение с текстом
        """
        if not text or not text.strip():
            raise ValueError("text must be non-empty for inline message")

        chat_id = message.chat.id
        bot = message.bot

        # Удалить предыдущее меню
        await self._clear_prev_menu(message)

        # Удалить сообщение пользователя (опционально)
        if clear_user:
            await self._safe_delete(bot, chat_id, message.message_id)

        # Показать inline
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=inline_kb)

    # ------------------------------------------------------------------
    # TYPE C — Reply → Reply с текстом (пошаговые сценарии)
    # ------------------------------------------------------------------

    async def show_with_text(
        self, 
        message: Message, 
        text: str, 
        kb: ReplyKeyboardMarkup
    ) -> None:
        """
        Type C — Reply → Reply с видимым текстом
        
        Для FSM/wizard когда нужно показать вопрос/инструкцию.
        Сообщение НЕ удаляется сразу.
        """
        if not text or not text.strip():
            raise ValueError("text must be non-empty")

        chat_id = message.chat.id

        # Удалить предыдущее меню
        await self._clear_prev_menu(message)

        # Отправить с текстом (не удаляем!)
        msg = await message.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb,
        )

        # Сохраняем для будущей очистки
        await self._set_last_menu_id(chat_id, msg.message_id)

    # ------------------------------------------------------------------
    # Inline helpers
    # ------------------------------------------------------------------

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
        except TelegramBadRequest:
            pass

    async def delete_inline(self, message: Message) -> None:
        """Удаление inline-сообщения."""
        await self._safe_delete(message.bot, message.chat.id, message.message_id)

    async def inline_to_menu(
        self, 
        message: Message, 
        kb: ReplyKeyboardMarkup
    ) -> None:
        """
        Inline → Reply (возврат из inline в меню)
        
        Вызывается из callback_query.message
        """
        # Удаляем inline-сообщение
        await self._safe_delete(message.bot, message.chat.id, message.message_id)
        
        # Показываем меню (navigate сам всё сделает)
        await self.navigate(message, kb)


