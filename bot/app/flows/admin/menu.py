from aiogram import Router, types
from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.auth import get_user_role
from bot.app.keyboards.admin import (
    admin_main,
    admin_settings,
    admin_schedule,
    admin_clients,
)

router = Router()


def setup(menu):
    @router.message()
    async def admin_reply(message: types.Message):
        role = await get_user_role(message.from_user.id)
        if role != "admin":
            return

        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text = message.text

        # --- MAIN → подменю ---
        if text == t("admin:main:settings", lang):
            await menu.navigate(
                message,
                t("admin:main:settings", lang),
                admin_settings(lang)
            )

        elif text == t("admin:main:schedule", lang):
            await menu.navigate(
                message,
                t("admin:main:schedule", lang),
                admin_schedule(lang)
            )

        elif text == t("admin:main:clients", lang):
            await menu.navigate(
                message,
                t("admin:main:clients", lang),
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
                "🏠",  # или t("admin:main:title", lang)
                admin_main(lang)
            )

    return router
