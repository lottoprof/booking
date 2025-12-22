import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Update
from aiogram.filters import Command

from pathlib import Path

from bot.app.config import BOT_TOKEN
from bot.app.i18n.loader import load_messages, t, DEFAULT_LANG
from bot.app.keyboards.common import language_inline
from bot.app.utils.state import user_lang

from bot.app.keyboards.admin import (
    admin_main,
    admin_settings,
    admin_schedule,
    admin_clients,
)
from aiogram.types import ReplyKeyboardRemove

from bot.app.flows.admin.menu import admin_menu
#from bot.app.flows.specialist.menu import specialist_menu
#from bot.app.flows.client.menu import client_menu

from bot.app.auth import get_user_role

BOT_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

load_messages(BOT_DIR / "i18n" / "messages.txt")

async def switch_kb(message: types.Message, kb):
    # 1. убрать старую клавиатуру
    await message.answer(
        "\u200b",
        reply_markup=ReplyKeyboardRemove()
    )
    # 2. показать новую клавиатуру
    await message.answer(
        "\u200b",
        reply_markup=kb
    )

# ===============================
# HANDLERS
# ===============================

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    tg_id = message.from_user.id
    lang = user_lang.get(tg_id)

    if not lang:
        kb = language_inline()
        if kb:
            await message.answer(
                t("common:lang:choose", DEFAULT_LANG),
                reply_markup=kb
            )
            return
        lang = DEFAULT_LANG
        user_lang[tg_id] = lang

    await route_by_role(message, lang)


@dp.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    lang = callback.data.split(":", 1)[1]

    user_lang[tg_id] = lang

    await callback.message.delete()
    await callback.answer()

    await route_by_role(callback.message, lang)

# ===============================
# ADMIN REPLY BUTTONS
# ===============================

@dp.message()
async def admin_reply_router(message: types.Message):
    role = await get_user_role(message.from_user.id)
    if role != "admin":
        return

    lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
    text = message.text

    if text == t("admin:main:settings", lang):
        await switch_kb(message, admin_settings(lang))

    elif text == t("admin:main:schedule", lang):
        await switch_kb(message, admin_schedule(lang))

    elif text == t("admin:main:clients", lang):
        await switch_kb(message, admin_clients(lang))

    elif text in (
        t("admin:settings:back", lang),
        t("admin:schedule:back", lang),
        t("admin:clients:back", lang),
    ):
        await switch_kb(message, admin_main(lang))

# ===============================
# ROUTER
# ===============================
ROLE_HANDLERS = {
    "admin": admin_menu,
    # "specialist": specialist_menu,
    # "client": client_menu,
}

async def route_by_role(message: types.Message, lang: str):
    role = await get_user_role(message.from_user.id)
    handler = ROLE_HANDLERS.get(role)
    
    if handler:
        await handler(message, lang)
    else:
        # TODO: client_menu когда будет готов
        await message.answer(f"Role: {role} (menu not implemented)")


# ===============================
# GATEWAY ENTRYPOINT
# ===============================

async def process_update(update_data: dict):
    """
    Единственная точка входа для gateway.
    """
    try:
        update = Update.model_validate(update_data)
    except Exception as e:
        logger.warning("Invalid Telegram update: %s", e)
        return

    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Error while processing Telegram update")

