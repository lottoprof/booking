# bot/app/flows/client/menu.py
"""
Логика навигации клиентского меню (Reply → Reply).
"""

from aiogram.types import Message

from bot.app.keyboards.client import (
    client_main,
)
from bot.app.i18n.loader import t


class ClientMenuFlow:

    def __init__(self, menu_controller):
        self.mc = menu_controller

    # ------------------------------------------------------------------
    # Main menu
    # ------------------------------------------------------------------

    async def show_main(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            client_main(lang),
            title=t("client:main:title", lang),
            menu_context=None  # у клиента пока один уровень
        )

    async def back_to_main(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            client_main(lang),
            title=t("client:main:title", lang),
            menu_context=None
        )

