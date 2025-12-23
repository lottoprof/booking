from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


class MenuController:
    """
    UI-контроллер навигации Telegram-бота.
    """

    def __init__(self):
        # chat_id -> message_id меню
        self.last_menu_message: dict[int, int] = {}

    async def clear_user_message(self, message: Message):
        try:
            await message.delete()
        except TelegramBadRequest:
            pass

    async def show_reply_menu(self, message: Message, kb):
        chat_id = message.chat.id
        last_id = self.last_menu_message.get(chat_id)

        if last_id:
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=last_id,
                    reply_markup=kb
                )
                return
            except TelegramBadRequest:
                pass

        # первый показ меню (ОДИН раз)
        msg = await message.answer(" ", reply_markup=kb)
        self.last_menu_message[chat_id] = msg.message_id

    async def navigate(self, message: Message, kb):
        """
        Reply → Reply
        """
        await self.clear_user_message(message)
        await self.show_reply_menu(message, kb)

    async def finish_to_inline(self, message: Message, text: str, inline_kb):
        """
        Reply → Inline
        """
        await self.clear_user_message(message)

        # удалить reply-меню, если было
        msg_id = self.last_menu_message.pop(message.chat.id, None)
        if msg_id:
            try:
                await message.bot.delete_message(message.chat.id, msg_id)
            except TelegramBadRequest:
                pass

        await message.answer(text, reply_markup=inline_kb)

