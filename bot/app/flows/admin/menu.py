from aiogram import types
from bot.app.keyboards.admin import (
    admin_main,
    admin_settings,
    admin_schedule,
    admin_clients,
)
from bot.app.i18n.loader import t


async def admin_menu(message: types.Message, lang: str):
    await message.answer(
        t("admin:main:settings", lang),
        reply_markup=admin_main(lang)
    )


async def admin_menu_router(message: types.Message, lang: str):
    text = message.text

    # --- MAIN ---
    if text == t("admin:main:settings", lang):
        await message.answer(
            t("admin:main:settings", lang),
            reply_markup=admin_settings(lang)
        )
        return

    if text == t("admin:main:schedule", lang):
        await message.answer(
            t("admin:main:schedule", lang),
            reply_markup=admin_schedule(lang)
        )
        return

    if text == t("admin:main:clients", lang):
        await message.answer(
            t("admin:main:clients", lang),
            reply_markup=admin_clients(lang)
        )
        return

    # --- BACK ---
    if text in (
        t("admin:settings:back", lang),
        t("admin:schedule:back", lang),
        t("admin:clients:back", lang),
    ):
        await message.answer(
            t("admin:main:settings", lang),
            reply_markup=admin_main(lang)
        )
        return

