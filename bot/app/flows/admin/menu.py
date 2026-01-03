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
    admin_rooms,
    admin_specialists,
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
            title=t("admin:main:title", lang),
            menu_context=None  # очищаем контекст
        )

    async def back_to_main(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_main(lang),
            title=t("admin:main:title", lang),
            menu_context=None
        )

    # ------------------------------------------------------------------
    # Main → Level 1
    # ------------------------------------------------------------------

    async def to_settings(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_settings(lang),
            title=t("admin:settings:title", lang),
            menu_context=None  # settings — промежуточный уровень
        )

    async def to_schedule(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_schedule(lang),
            title=t("admin:schedule:title", lang),
            menu_context="schedule"
        )

    async def to_clients(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message, 
            admin_clients(lang),
            title=t("admin:clients:title", lang),
            menu_context="clients"
        )

    # ------------------------------------------------------------------
    # Settings → Level 2
    # ------------------------------------------------------------------

    async def to_locations(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_locations(lang),
            title=t("admin:locations:title", lang),
            menu_context="locations"
        )

    async def to_services(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_services(lang),
            title=t("admin:services:title", lang),
            menu_context="services"
        )

    async def to_rooms(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_rooms(lang),
            title=t("admin:rooms:title", lang),
            menu_context="rooms"
        )

    async def to_specialists(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_specialists(lang),
            title=t("admin:specialists:title", lang),
            menu_context="specialists"
        )

    async def back_to_settings(self, message: Message, lang: str) -> None:
        await self.mc.show(
            message,
            admin_settings(lang),
            title=t("admin:settings:title", lang),
            menu_context=None  # очищаем при возврате
        )

