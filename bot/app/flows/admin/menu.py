"""
bot/app/flows/admin/menu.py

Логика навигации админ-меню (Reply→Reply).
"""

from aiogram.types import Message

from bot.app.keyboards.admin import (
    admin_main,
    admin_settings,
    admin_schedule,
    admin_clients,
    admin_locations,
    admin_services,
)
from bot.app.i18n.loader import t


class AdminMenuFlow:

    def __init__(self, menu_controller):
        self.mc = menu_controller

    # ------------------------------------------------------------------
    # Main menu
    # ------------------------------------------------------------------

    async def show_main(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_main(lang),
            title=t("admin:main:title", lang)
        )

    async def back_to_main(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_main(lang),
            title=t("admin:main:title", lang)
        )

    # ------------------------------------------------------------------
    # Main → Level 1
    # ------------------------------------------------------------------

    async def to_settings(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_settings(lang),
            title=t("admin:settings:title", lang)
        )

    async def to_schedule(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_schedule(lang),
            title=t("admin:schedule:title", lang)
        )

    async def to_clients(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_clients(lang),
            title=t("admin:clients:title", lang)
        )

    # ------------------------------------------------------------------
    # Settings → Level 2
    # ------------------------------------------------------------------

    async def to_locations(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_locations(lang),
            title=t("admin:locations:title", lang)
        )

    async def back_to_settings(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_settings(lang),
            title=t("admin:settings:title", lang)
        )

    async def to_services(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_services(lang),
            title=t("admin:services:title", lang)
        )

