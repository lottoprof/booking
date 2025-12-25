# bot/app/handlers/admin_reply.py

from aiogram import Router, types
from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.keyboards.admin import (
    admin_main,
    admin_settings,
    admin_schedule,
    admin_clients,
)

router = Router()


def setup(menu, get_user_role):
    """
    Настройка роутера с инъекцией зависимостей.
    
    Args:
        menu: MenuController для управления навигацией
        get_user_role: функция получения роли пользователя
    """
    
    @router.message()
    async def admin_reply(message: types.Message):
        tg_id = message.from_user.id
        role = get_user_role(tg_id)
        
        if role != "admin":
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)
        text = message.text

        # --- MAIN → подменю ---
        if text == t("admin:main:settings", lang):
           await menu.navigate(
                message,
                admin_settings(lang)
            )

        elif text == t("admin:main:schedule", lang):
            await menu.navigate(
                message,
                admin_schedule(lang)
            )

        elif text == t("admin:main:clients", lang):
            await menu.navigate(
                message,
                admin_clients(lang)
            )

        # --- BACK → главное меню ---
        elif text in (
            t("admin:settings:back", lang),
            t("admin:schedule:back", lang),
            t("admin:clients:back", lang),
        ):
            await menu.navigate(
                message,
                admin_main(lang)
            )

    return router

