# bot/app/utils/menucontroller.py
# Типы поведения кнопок

from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest


ZERO = "\u2060"  # обязательный непустой текст


class MenuController:
    """
    UI-контроллер навигации Telegram-бота.
    Отвечает ТОЛЬКО за:
    - очистку чата
    - смену reply-меню
    - переход Reply -> Inline

    Не знает:
    - ролей
    - бизнес-логики
    - FSM
    """

    def __init__(self):
        # chat_id -> message_id последнего меню бота
        self.last_menu_message: dict[int, int] = {}

    async def clear(self, message: Message):
        chat_id = message.chat.id

        # удалить сообщение пользователя
        try:
            await message.delete()
        except TelegramBadRequest:
            pass

        # удалить предыдущее меню бота
        msg_id = self.last_menu_message.get(chat_id)
        if msg_id:
            try:
                await message.bot.delete_message(chat_id, msg_id)
            except TelegramBadRequest:
                pass
            self.last_menu_message.pop(chat_id, None)

    async def show_reply_menu(self, message: Message, kb):
        msg = await message.answer(
            ZERO,
            reply_markup=kb
        )
        self.last_menu_message[message.chat.id] = msg.message_id

    async def navigate(self, message: Message, kb):
        """
        Тип A — Reply → Reply
        Очистка + показ нового меню
        """
        await self.clear(message)
        await self.show_reply_menu(message, kb)

    async def finish_to_inline(self, message: Message, text: str, inline_kb):
        """
        Тип B — Reply → Inline
        Очистка + показ inline-сообщения
        """
        await self.clear(message)
        await message.answer(
            text or ZERO,
            reply_markup=inline_kb
        )

