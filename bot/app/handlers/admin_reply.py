# bot/app/handlers/admin_reply.py

from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


class MenuController:
    """
    UI-контроллер навигации Telegram-бота.

    Принцип работы:
    - При переходе удаляется сообщение пользователя
    - Удаляется предыдущее сообщение бота (заголовок меню)
    - Отправляется новое сообщение с заголовком и клавиатурой
    - message_id сохраняется для удаления при следующем переходе
    """

    def __init__(self):
        # chat_id -> message_id последнего меню-сообщения бота
        self.last_menu_message: dict[int, int] = {}

    async def _clear(self, message: Message):
        """
        Очистка чата:
        1. Удалить сообщение пользователя
        2. Удалить предыдущее меню бота (если есть)
        """
        chat_id = message.chat.id

        # удалить сообщение пользователя
        try:
            await message.delete()
        except TelegramBadRequest:
            pass

        # удалить предыдущее меню бота
        msg_id = self.last_menu_message.pop(chat_id, None)
        if msg_id:
            try:
                await message.bot.delete_message(chat_id, msg_id)
            except TelegramBadRequest:
                pass

    async def navigate(self, message: Message, text: str, kb):
        """
        Тип A — Reply → Reply

        Смена меню с очисткой чата:
        - удаляет сообщение пользователя
        - удаляет предыдущее меню бота
        - отправляет новое сообщение с заголовком и клавиатурой
        """
        await self._clear(message)

        # отправляем новое меню с заголовком
        msg = await message.answer(text, reply_markup=kb)
        self.last_menu_message[message.chat.id] = msg.message_id

    async def finish_to_inline(self, message: Message, text: str, inline_kb):
        """
        Тип B — Reply → Inline

        Завершение reply-меню и переход к inline-взаимодействию:
        - удаляет сообщение пользователя
        - удаляет reply-меню
        - показывает inline-сообщение (не сохраняем в last_menu)
        """
        await self._clear(message)
        await message.answer(text, reply_markup=inline_kb)

    async def show_without_clear(self, message: Message, text: str, kb):
        """
        Тип C — Reply → Reply без очистки

        Традиционный выбор в пошаговых сценариях:
        - сообщение пользователя НЕ удаляется
        - предыдущее меню НЕ удаляется
        - показывается новое меню
        """
        msg = await message.answer(text, reply_markup=kb)
        self.last_menu_message[message.chat.id] = msg.message_id

