"""
bot/app/flows/admin/menu.py

ЛОГИКА — решает какое меню показать.

Знает о структуре меню админа и правилах переходов.
Использует MenuController для отправки (не знает КАК отправлять).
Использует keyboards для получения форм (не знает КАК они устроены).
"""

from aiogram.types import Message

from bot.app.keyboards.admin import (
    admin_main,
    admin_settings,
    admin_schedule,
    admin_clients,
)


class AdminMenuFlow:
    """
    Логика навигации админ-меню.
    
    Методы соответствуют пунктам меню.
    Каждый метод знает КУДА перейти, но не КАК.
    """

    def __init__(self, menu_controller):
        self.mc = menu_controller

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def show_main(self, message: Message, lang: str) -> None:
        """Показать главное меню админа."""
        await self.mc.show(message, admin_main(lang))

    # ------------------------------------------------------------------
    # Main → Submenus
    # ------------------------------------------------------------------

    async def to_settings(self, message: Message, lang: str) -> None:
        """Главное меню → Настройки."""
        await self.mc.show(message, admin_settings(lang))

    async def to_schedule(self, message: Message, lang: str) -> None:
        """Главное меню → Расписание."""
        await self.mc.show(message, admin_schedule(lang))

    async def to_clients(self, message: Message, lang: str) -> None:
        """Главное меню → Клиенты."""
        await self.mc.show(message, admin_clients(lang))

    # ------------------------------------------------------------------
    # Back → Main
    # ------------------------------------------------------------------

    async def back_to_main(self, message: Message, lang: str) -> None:
        """Любое подменю → Главное меню."""
        await self.mc.show(message, admin_main(lang))


