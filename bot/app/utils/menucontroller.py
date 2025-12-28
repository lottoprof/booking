"""
bot/app/utils/menucontroller.py

UI-контроллер навигации Telegram-бота.

Контракт (tg_kbrd.md v2.1):
- В чате ровно ОДИН якорь ReplyKeyboard
- ReplyKeyboardRemove ЗАПРЕЩЁН между меню
- Порядок: send → delete

Type B разделён на:
- B1 (show_inline_readonly) — для списков/выбора, Reply-якорь СОХРАНЯЕТСЯ
- B2 (show_inline_input) — для форм/ввода, Reply-якорь УДАЛЯЕТСЯ, IME активен
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
    
    Хранит в Redis:
    - last_menu_message_id (якорь Reply-клавиатуры)
    - inline messages для очистки
    - current_menu контекст
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

    def _current_menu_key(self, chat_id: int) -> str:
        return f"tg:current_menu:{chat_id}"

    # ------------------------------------------------------------------
    # Redis: current menu context
    # ------------------------------------------------------------------

    async def set_menu_context(self, chat_id: int, menu_name: str) -> None:
        """Установить текущий контекст меню."""
        await self.redis.set(self._current_menu_key(chat_id), menu_name)

    async def get_menu_context(self, chat_id: int) -> str | None:
        """Получить текущий контекст меню."""
        return await self.redis.get(self._current_menu_key(chat_id))

    async def clear_menu_context(self, chat_id: int) -> None:
        """Очистить контекст меню."""
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
        title: str = "📋",
        menu_context: str | None = None
    ) -> None:
        """
        Показать ReplyKeyboard (Type A).
        
        Алгоритм:
        1. Отправить новое меню (клавиатура появляется)
        2. Сохранить якорь в Redis
        3. Удалить старый якорь
        4. Удалить сообщение пользователя
        
        Args:
            menu_context: имя меню для контекста (locations, services, etc.)
                         если None — контекст очищается
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

        # 3. Установить/очистить контекст меню
        if menu_context:
            await self.set_menu_context(chat_id, menu_context)
        else:
            await self.clear_menu_context(chat_id)

        # 4. Удалить старый якорь бота
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)

        # 5. Удалить сообщение пользователя
        await self._safe_delete(bot, chat_id, user_msg_id)

    # Alias для совместимости
    async def navigate(self, message: Message, kb: ReplyKeyboardMarkup) -> None:
        await self.show(message, kb)

    # ------------------------------------------------------------------
    # Type B1: Reply → Inline (readonly — списки, выбор)
    # ------------------------------------------------------------------

    async def show_inline_readonly(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        """
        Показать InlineKeyboard для ВЫБОРА (Type B1).
        
        Reply-якорь СОХРАНЯЕТСЯ — IME не появляется.
        Используется для:
        - Списки с пагинацией
        - Выбор из вариантов
        - Просмотр данных
        
        Алгоритм:
        1. Отправить inline-сообщение
        2. Трекать для очистки
        3. Удалить сообщение пользователя
        4. Reply-якорь НЕ удаляется!
        """
        chat_id = message.chat.id
        bot = message.bot
        user_msg_id = message.message_id

        # 1. Отправить inline-сообщение
        inline_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb
        )

        # 2. Трекаем inline для очистки
        await self._add_inline_id(chat_id, inline_msg.message_id)

        # 3. Удалить сообщение пользователя
        await self._safe_delete(bot, chat_id, user_msg_id)

        # Reply-якорь НЕ удаляется — клавиатура остаётся активной
        
        return inline_msg

    # ------------------------------------------------------------------
    # Type B2: Reply → Inline (input — формы, ввод данных)
    # ------------------------------------------------------------------

    async def show_inline_input(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        """
        Показать InlineKeyboard для ВВОДА (Type B2).
        
        Reply-якорь УДАЛЯЕТСЯ — IME активен для ввода текста.
        Используется для:
        - Формы создания/редактирования
        - Ввод текстовых данных
        - FSM wizard steps
        
        Алгоритм:
        1. Отправить inline-сообщение
        2. Трекать для очистки
        3. Удалить сообщение пользователя
        4. Удалить Reply-якорь (ПОСЛЕДНИМ!)
        5. Очистить якорь в Redis
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

        # 3. Удалить сообщение пользователя СНАЧАЛА
        await self._safe_delete(bot, chat_id, user_msg_id)

        # 4. Удалить старый reply-якорь ПОСЛЕДНИМ
        # (inline уже на экране, IME появится для ввода)
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)

        # 5. Очистить якорь (inline НЕ является якорем)
        await self._del_menu_id(chat_id)
        
        return inline_msg

    # ------------------------------------------------------------------
    # Backward compatibility: show_inline → show_inline_input
    # ------------------------------------------------------------------

    async def show_inline(
        self,
        message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> Message:
        """
        DEPRECATED: Используйте show_inline_readonly() или show_inline_input().
        
        Сохранено для обратной совместимости.
        По умолчанию ведёт себя как show_inline_input (старое поведение).
        """
        logger.warning(
            "show_inline() is deprecated. "
            "Use show_inline_readonly() for lists or show_inline_input() for forms."
        )
        return await self.show_inline_input(message, text, kb)

    # ------------------------------------------------------------------
    # Inline → Reply (возврат из inline)
    # ------------------------------------------------------------------

    async def back_to_reply(
        self, 
        callback_message: Message, 
        kb: ReplyKeyboardMarkup,
        title: str = "📋",
        menu_context: str | None = None
    ) -> None:
        """
        Вернуться из Inline в Reply меню.
        Удаляет ВСЕ tracked inline-сообщения.
        
        Args:
            menu_context: если указан — устанавливает контекст,
                         если None — сохраняет текущий контекст
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

        # 3. Обновить контекст если указан
        if menu_context is not None:
            await self.set_menu_context(chat_id, menu_context)

        # 4. Удалить ВСЕ tracked inline-сообщения
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
        """Обновить inline-сообщение (пагинация, смена состояния)."""
        try:
            await callback_message.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            pass

    # ------------------------------------------------------------------
    # Inline → Inline + активация IME (переход к вводу)
    # ------------------------------------------------------------------

    async def edit_inline_input(
        self,
        callback_message: Message,
        text: str,
        kb: InlineKeyboardMarkup,
    ) -> None:
        """
        Обновить inline-сообщение И активировать режим ввода.
        
        Используется когда пользователь нажал "Редактировать" из карточки.
        Reply-якорь удаляется — IME появляется.
        
        Сценарий:
        - Список (B1, якорь сохранён) → Карточка (edit_inline) → 
        - Редактировать (edit_inline_input, якорь удаляется, IME активен)
        """
        chat_id = callback_message.chat.id
        bot = callback_message.bot
        
        # 1. Обновить inline-сообщение
        try:
            await callback_message.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            pass
        
        # 2. Удалить Reply-якорь если есть (активирует IME)
        old_menu_id = await self._get_menu_id(chat_id)
        if old_menu_id:
            await self._safe_delete(bot, chat_id, old_menu_id)
            await self._del_menu_id(chat_id)
            logger.debug(f"edit_inline_input: deleted reply anchor, IME activated")

    # ------------------------------------------------------------------
    # FSM: новое inline в процессе flow (уже без Reply-якоря)
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
        
        Используется когда Reply-якорь уже удалён (после show_inline_input).
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

