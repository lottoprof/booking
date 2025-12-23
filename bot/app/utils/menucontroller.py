# bot/app/utils/menucontroller.py
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


class MenuController:
    """
    UI-контроллер навигации Telegram-бота.

    Управляет:
    - очисткой чата (удаление сообщений пользователя и предыдущего меню)
    - сменой reply-клавиатур
    - переходом Reply → Inline

    Не принимает решений о сценариях — только выполняет технические действия.
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
    async def _show_reply_menu(self, message: Message, kb):
        msg = await message.answer(".", reply_markup=kb)
        self.last_menu_message[message.chat.id] = msg.message_id
        # сразу удаляем сообщение — клавиатура остаётся
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass

    async def navigate(self, message: Message, kb):
        """
        Тип A — Reply → Reply

        Смена меню с очисткой чата:
        - удаляет сообщение пользователя
        - удаляет предыдущее меню бота
        - показывает новое меню
        """
        await self._clear(message)
        await self._show_reply_menu(message, kb)

    async def finish_to_inline(self, message: Message, text: str, inline_kb):
        """
        Тип B — Reply → Inline

        Завершение reply-меню и переход к inline-взаимодействию:
        - удаляет сообщение пользователя
        - удаляет reply-меню
        - показывает inline-сообщение
        """
        await self._clear(message)
        await message.answer(text, reply_markup=inline_kb)

    async def show_without_clear(self, message: Message, kb):
        """
        Тип C — Reply → Reply без очистки

        Традиционный выбор в пошаговых сценариях:
        - сообщение пользователя НЕ удаляется
        - предыдущее меню НЕ удаляется
        - показывается новое меню
        """
        msg = await message.answer(
            "\u200b",
            reply_markup=kb
        )
        self.last_menu_message[message.chat.id] = msg.message_id

