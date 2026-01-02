"""
bot/app/utils/menucontroller.py

UI-контроллер навигации Telegram-бота.
DEBUG VERSION - добавлено логирование для диагностики.
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
    """

    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError("REDIS_URL is not set")
        self.redis = redis.from_url(redis_url, decode_responses=True)
        logger.info(f"MenuController initialized with redis_url: {redis_url[:20]}...")

    # ------------------------------------------------------------------
    # Redis keys
    # ------------------------------------------------------------------

    def _menu_key(self, chat_id: int) -> str:
        return f"tg:menu:{chat_id}"

    def _inline_key(self, chat_id: int) -> str:
        return f"tg:inline:{chat_id}"

    def _current_menu_key(self, chat_id: int) -> str:
        return f"tg:current_menu:{chat_id}"

    # ------------------------------------------------------------------
    # Redis: current menu context
    # ------------------------------------------------------------------

    async def set_menu_context(self, chat_id: int, menu_name: str) -> None:
        await self.redis.set(self._current_menu_key(chat_id), menu_name)

    async def get_menu_context(self, chat_id: int) -> str | None:
        return await self.redis.get(self._current_menu_key(chat_id))

    async def clear_menu_context(self, chat_id: int) -> None:
        await self.redis.delete(self._current_menu_key(chat_id))

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
        await self.redis.rpush(self._inline_key(chat_id), str(msg_id))

    async def _get_inline_ids(self, chat_id: int) -> list[int]:
        vals = await self.redis.lrange(self._inline_key(chat_id), 0, -1)
        return [int(v) for v in vals] if vals else []

    async def _clear_inline_ids(self, chat_id: int) -> None:
        await self.redis.delete(self._inline_key(chat_id))

    # ------------------------------------------------------------------
    # Global reset (for /start)
    # ------------------------------------------------------------------

    async def reset(self, chat_id: int) -> None:
        """
        Полный сброс навигационного состояния чата.
        """
        logger.info(f"[RESET] Starting reset for chat_id={chat_id}")
        try:
            await self._del_menu_id(chat_id)
            logger.info(f"[RESET] Deleted menu_id")
            await self._clear_inline_ids(chat_id)
            logger.info(f"[RESET] Cleared inline_ids")
            await self.clear_menu_context(chat_id)
            logger.info(f"[RESET] Cleared menu_context")
            logger.info(f"[RESET] Complete for chat_id={chat_id}")
        except Exception as e:
            logger.exception(f"[RESET] ERROR: {e}")
            raise

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------

    async def _safe_delete(self, bot, chat_id: int, msg_id: int) -> bool:
        try:
            await bot.delete_message(chat_id, msg_id)
            return True
        except TelegramBadRequest as e:
            logger.debug(f"[DELETE] Failed to delete msg {msg_id}: {e}")
            return False

    async def _delete_previous_menu(self, message: Message) -> None:
        chat_id = message.chat.id
        old_id = await self._get_menu_id(chat_id)
        if old_id:
            await self._safe_delete(message.bot, chat_id, old_id)
            await self._del_menu_id(chat_id)

    async def _delete_all_inline(self, bot, chat_id: int) -> int:
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
        title: str = "📋",
        menu_context: str | None = None
    ) -> None:
        """
        Показать ReplyKeyboard (Type A).
        """
        chat_id = message.chat.id
        bot = message.bot
        
        logger.info(f"[SHOW] Starting: chat_id={chat_id}, title={title}, context={menu_context}")
        
        try:
            old_menu_id = await self._get_menu_id(chat_id)
            user_msg_id = message.message_id
            logger.info(f"[SHOW] old_menu_id={old_menu_id}, user_msg_id={user_msg_id}")

            # 1. Отправить новое меню
            logger.info(f"[SHOW] Sending new menu...")
            msg = await bot.send_message(
                chat_id=chat_id,
                text=title,
                reply_markup=kb
            )
            logger.info(f"[SHOW] Menu sent, new_msg_id={msg.message_id}")
            
            # 2. Сохранить новый якорь
            await self._set_menu_id(chat_id, msg.message_id)
            logger.info(f"[SHOW] Saved new menu_id to Redis")

            # 3. Установить/очистить контекст меню
            if menu_context:
                await self.set_menu_context(chat_id, menu_context)
            else:
                await self.clear_menu_context(chat_id)
            logger.info(f"[SHOW] Menu context updated")

            # 4. Удалить старый якорь бота
            if old_menu_id:
                await self._safe_delete(bot, chat_id, old_menu_id)
                logger.info(f"[SHOW] Deleted old menu")

            # 5. Удалить сообщение пользователя
            deleted = await self._safe_delete(bot, chat_id, user_msg_id)
            logger.info(f"[SHOW] Deleted user message: {deleted}")
            
            logger.info(f"[SHOW] Complete for chat_id={chat_id}")
            
        except Exception as e:
            logger.exception(f"[SHOW] ERROR: {e}")
            raise

    async def navigate(self, message: Message, kb: ReplyKeyboardMarkup) -> None:
        await self.show(message, kb)

    # ------------------------------------------------------------------
    # Type B1: Reply → Inline (readonly)
    # ------------------------------------------------------------------

    async def show_inline_readonly(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        chat_id = message.chat.id
        bot = message.bot
        user_msg_id = message.message_id

        logger.info(f"[SHOW_INLINE_RO] Starting: chat_id={chat_id}")

        # 1. Удалить предыдущие inline (если повторный вызов)
        deleted_old = await self._delete_all_inline(bot, chat_id)
        if deleted_old:
            logger.info(f"[SHOW_INLINE_RO] Deleted {deleted_old} old inline messages")

        # 2. Отправить новое inline сообщение
        inline_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb
        )
        logger.info(f"[SHOW_INLINE_RO] Sent inline, msg_id={inline_msg.message_id}")

        # 3. Трекать новое inline
        await self._add_inline_id(chat_id, inline_msg.message_id)
        
        # 4. Удалить сообщение пользователя
        await self._safe_delete(bot, chat_id, user_msg_id)
        
        logger.info(f"[SHOW_INLINE_RO] Complete")
        return inline_msg

    # ------------------------------------------------------------------
    # Type B2: Reply → Inline (input)
    # ------------------------------------------------------------------

    async def show_inline_input(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        chat_id = message.chat.id
        bot = message.bot
        
        old_menu_id = await self._get_menu_id(chat_id)
        user_msg_id = message.message_id

        logger.info(f"[SHOW_INLINE_INPUT] Starting: chat_id={chat_id}")

        # 1. Удалить предыдущие inline (если повторный вызов)
        deleted_old = await self._delete_all_inline(bot, chat_id)
        if deleted_old:
            logger.info(f"[SHOW_INLINE_INPUT] Deleted {deleted_old} old inline messages")

        # 2. Отправить новое inline сообщение
        inline_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb
        )
        logger.info(f"[SHOW_INLINE_INPUT] Sent inline, msg_id={inline_msg.message_id}")

        # 3. Трекать новое inline
        await self._add_inline_id(chat_id, inline_msg.message_id)
        
        # 4. Удалить сообщение пользователя
        await self._safe_delete(bot, chat_id, user_msg_id)

        # 5. Удалить Reply-якорь (активирует IME)
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)

        await self._del_menu_id(chat_id)
        
        logger.info(f"[SHOW_INLINE_INPUT] Complete")
        return inline_msg

    # ------------------------------------------------------------------
    # Backward compatibility
    # ------------------------------------------------------------------

    async def show_inline(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        logger.warning("show_inline() is deprecated")
        return await self.show_inline_input(message, text, kb)

    # ------------------------------------------------------------------
    # Inline → Reply
    # ------------------------------------------------------------------

    async def back_to_reply(
        self, 
        callback_message: Message, 
        kb: ReplyKeyboardMarkup,
        title: str = "📋",
        menu_context: str | None = None
    ) -> None:
        chat_id = callback_message.chat.id
        bot = callback_message.bot

        logger.info(f"[BACK_TO_REPLY] Starting: chat_id={chat_id}")

        # 1. Получить старый Reply-якорь (если есть)
        old_menu_id = await self._get_menu_id(chat_id)
        logger.info(f"[BACK_TO_REPLY] old_menu_id={old_menu_id}")

        # 2. Отправить новое Reply меню
        msg = await bot.send_message(
            chat_id=chat_id,
            text=title,
            reply_markup=kb
        )
        logger.info(f"[BACK_TO_REPLY] Sent new menu, msg_id={msg.message_id}")
        
        # 3. Сохранить новый якорь
        await self._set_menu_id(chat_id, msg.message_id)

        # 4. Установить контекст меню
        if menu_context is not None:
            await self.set_menu_context(chat_id, menu_context)

        # 5. Удалить ВСЕ inline сообщения
        deleted_inline = await self._delete_all_inline(bot, chat_id)
        logger.info(f"[BACK_TO_REPLY] Deleted {deleted_inline} inline messages")

        # 6. Удалить СТАРЫЙ Reply-якорь (КРИТИЧНО!)
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)
            logger.info(f"[BACK_TO_REPLY] Deleted old reply anchor {old_menu_id}")

        logger.info(f"[BACK_TO_REPLY] Complete")

    # ------------------------------------------------------------------
    # Inline → Inline
    # ------------------------------------------------------------------

    async def edit_inline(
        self,
        callback_message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> None:
        try:
            await callback_message.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            pass

    async def edit_inline_input(
        self,
        callback_message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> None:
        chat_id = callback_message.chat.id
        bot = callback_message.bot
        
        try:
            await callback_message.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            pass
        
        old_menu_id = await self._get_menu_id(chat_id)
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)
            await self._del_menu_id(chat_id)

    # ------------------------------------------------------------------
    # Show for chat (without Message object)
    # ------------------------------------------------------------------

    async def show_for_chat(
        self,
        bot,
        chat_id: int,
        kb: ReplyKeyboardMarkup,
        title: str = "📋",
        menu_context: str | None = None
    ) -> None:
        """
        Показать ReplyKeyboard по chat_id (без объекта Message).
        Используется после callback когда оригинальный Message удалён.
        """
        logger.info(f"[SHOW_FOR_CHAT] Starting: chat_id={chat_id}, title={title}")
        
        try:
            old_menu_id = await self._get_menu_id(chat_id)
            logger.info(f"[SHOW_FOR_CHAT] old_menu_id={old_menu_id}")

            # 1. Отправить новое меню
            msg = await bot.send_message(
                chat_id=chat_id,
                text=title,
                reply_markup=kb
            )
            logger.info(f"[SHOW_FOR_CHAT] Menu sent, new_msg_id={msg.message_id}")
            
            # 2. Сохранить новый якорь
            await self._set_menu_id(chat_id, msg.message_id)

            # 3. Установить/очистить контекст меню
            if menu_context:
                await self.set_menu_context(chat_id, menu_context)
            else:
                await self.clear_menu_context(chat_id)

            # 4. Удалить старый якорь бота
            if old_menu_id:
                await self._safe_delete(bot, chat_id, old_menu_id)
                logger.info(f"[SHOW_FOR_CHAT] Deleted old menu")
            
            logger.info(f"[SHOW_FOR_CHAT] Complete for chat_id={chat_id}")
            
        except Exception as e:
            logger.exception(f"[SHOW_FOR_CHAT] ERROR: {e}")
            raise

    # ------------------------------------------------------------------
    # FSM flow
    # ------------------------------------------------------------------

    async def send_inline_in_flow(
        self,
        bot,
        chat_id: int,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        inline_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb
        )
        await self._add_inline_id(chat_id, inline_msg.message_id)
        return inline_msg
