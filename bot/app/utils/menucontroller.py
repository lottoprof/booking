import logging
import os

from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Технический текст для устойчивой ReplyKeyboard (Android)
ZERO_WIDTH_SPACE = "\u200b"


class MenuController:
    """
    UI-контроллер навигации Telegram-бота.

    Контракт v1 (кратко):
    - Один якорь ReplyKeyboard на чат
    - Type A (Reply→Reply): user message НЕ удаляем, ZWS обязателен
    - Type B (Reply→Inline): user message МОЖНО удалить
    - Никаких delete "через одно"
    """

    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL is not set")

        # Один клиент Redis на контроллер
        self.redis = redis.from_url(
            redis_url,
            decode_responses=True,
        )

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
    # Clear helpers
    # ------------------------------------------------------------------

    async def _clear_user_message(self, message: Message) -> None:
        """
        Удаление сообщения пользователя.
        РАЗРЕШЕНО ТОЛЬКО в Type B.
        """
        try:
            await message.delete()
            logger.info(
                "UI: deleted user message %s in chat %s",
                message.message_id,
                message.chat.id,
            )
        except TelegramBadRequest as e:
            logger.warning(
                "UI: failed to delete user message %s: %s",
                message.message_id,
                e,
            )

    async def _clear_bot_menu(self, message: Message) -> None:
        """
        Удаление якоря ReplyKeyboard (ОДНОГО).
        """
        chat_id = message.chat.id
        menu_id = await self._get_last_menu_id(chat_id)

        if not menu_id:
            logger.debug("UI: no bot menu to delete for chat %s", chat_id)
            return

        try:
            await message.bot.delete_message(chat_id, menu_id)
            logger.info(
                "UI: deleted bot menu %s in chat %s",
                menu_id,
                chat_id,
            )
        except TelegramBadRequest as e:
            logger.warning(
                "UI: failed to delete bot menu %s: %s",
                menu_id,
                e,
            )
        finally:
            await self._del_last_menu_id(chat_id)

    # ------------------------------------------------------------------
    # TYPE A — Reply → Reply (основная навигация)
    # ------------------------------------------------------------------

    async def navigate(self, message: Message, kb) -> None:
        """
        Type A — Reply → Reply (устойчивый)

        - сообщение пользователя НЕ удаляется
        - удаляется ТОЛЬКО предыдущее меню бота
        - новое меню отправляется как ZWS + ReplyKeyboard
        """
        # Guard: navigate нельзя вызывать из inline-контекста
        if message.reply_to_message:
            logger.warning(
                "UI: navigate() called with reply_to_message (possible inline misuse)"
            )

        # 1. удалить предыдущий якорь
        await self._clear_bot_menu(message)

        # 2. отправить новое меню
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            text=ZERO_WIDTH_SPACE,
            reply_markup=kb,
        )

        # 3. сохранить якорь
        await self._set_last_menu_id(message.chat.id, msg.message_id)

        logger.info(
            "UI: saved bot menu %s for chat %s",
            msg.message_id,
            message.chat.id,
        )

    # ------------------------------------------------------------------
    # TYPE B — Reply → Inline (вход в inline-сценарий)
    # ------------------------------------------------------------------

    async def finish_to_inline(
        self,
        message: Message,
        text: str,
        inline_kb,
        *,
        clear_user: bool = True,
    ) -> None:
        """
        Type B — Reply → Inline

        - опционально удаляет сообщение пользователя
        - удаляет reply-меню
        - показывает inline-сообщение
        """
        if clear_user:
            await self._clear_user_message(message)

        await self._clear_bot_menu(message)

        await message.answer(text, reply_markup=inline_kb)

        logger.info(
            "UI: entered inline mode in chat %s",
            message.chat.id,
        )

    # ------------------------------------------------------------------
    # TYPE C — Reply → Reply без очистки (пошаговые сценарии)
    # ------------------------------------------------------------------

    async def show_without_clear(self, message: Message, text: str, kb) -> None:
        """
        Type C — Reply → Reply без очистки

        ⚠ Использовать ТОЛЬКО в пошаговых сценариях.
        ⚠ Не предназначен для навигации меню.
        """
        msg = await message.answer(text, reply_markup=kb)
        await self._set_last_menu_id(message.chat.id, msg.message_id)

        logger.info(
            "UI: saved bot menu (type C) %s for chat %s",
            msg.message_id,
            message.chat.id,
        )

    # ------------------------------------------------------------------
    # INLINE — ЗАГЛУШКИ (централизованные точки)
    # ------------------------------------------------------------------

    async def show_inline(self, message: Message, text: str, inline_kb) -> None:
        """
        Inline — показ inline-сообщения.

        - ReplyKeyboard не используется
        - Redis-якорь не трогается
        """
        await message.answer(text, reply_markup=inline_kb)

        logger.debug("UI: show inline message in chat %s", message.chat.id)

    async def update_inline(self, message: Message, text: str, inline_kb) -> None:
        """
        Inline — обновление inline-сообщения (callback).
        """
        try:
            await message.edit_text(text, reply_markup=inline_kb)
            logger.debug(
                "UI: updated inline message %s",
                message.message_id,
            )
        except TelegramBadRequest as e:
            logger.warning(
                "UI: failed to update inline message %s: %s",
                message.message_id,
                e,
            )

    async def inline_finish_to_menu(self, message: Message, kb) -> None:
        """
        Inline → Reply (возврат в меню)

        - удаляет inline-сообщение
        - возвращает ReplyKeyboard через Type A
        """
        try:
            await message.delete()
        except TelegramBadRequest:
            pass

        await self.navigate(message, kb)

