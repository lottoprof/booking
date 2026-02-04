"""
bot/app/flows/specialist/menu.py

Navigation logic for specialist menu (Reply→Reply).
"""

from aiogram.types import Message

from bot.app.keyboards.specialist import (
    specialist_main,
    specialist_gcal,
)
from bot.app.i18n.loader import t


class SpecialistMenuFlow:

    def __init__(self, menu_controller):
        self.mc = menu_controller

    # ------------------------------------------------------------------
    # Main menu
    # ------------------------------------------------------------------

    async def show_main(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            specialist_main(lang),
            title=t("specialist:main:title", lang),
            menu_context=None
        )

    async def back_to_main(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            specialist_main(lang),
            title=t("specialist:main:title", lang),
            menu_context=None
        )

    # ------------------------------------------------------------------
    # Google Calendar submenu
    # ------------------------------------------------------------------

    async def to_gcal(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            specialist_gcal(lang),
            title=t("specialist:gcal:title", lang),
            menu_context="gcal"
        )
