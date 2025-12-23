# bot/app/main.py

import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Update, Message, CallbackQuery, TelegramObject

from bot.app.config import BOT_TOKEN
from bot.app.i18n.loader import load_messages, t, DEFAULT_LANG
from bot.app.keyboards.common import language_inline
from bot.app.keyboards.admin import admin_main
from bot.app.utils.state import user_lang
from bot.app.utils.menucontroller import MenuController

from bot.app.handlers import admin_reply
from bot.app.auth import get_user_role


BOT_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

menu = MenuController()

load_messages(BOT_DIR / "i18n" / "messages.txt")


# ===============================
# ENTRYPOINTS
# ===============================

@dp.message(Command("start"))
async def start_handler(message: Message):
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
async def language_callback(callback: CallbackQuery):
    tg_id = callback.from_user.id
    lang = callback.data.split(":", 1)[1]

    user_lang[tg_id] = lang

    # удаляем сообщение с inline выбором языка
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.answer()

    # ВАЖНО: передаём callback, а не callback.message
    await route_by_role(callback, lang)


# ===============================
# ROLE ROUTER (ENTRY ONLY)
# ===============================

async def admin_menu(message: Message, lang: str):
    """Первичный вход в админ-меню — тоже через MenuController."""
    msg = await message.answer(
        t("admin:main:settings", lang),
        reply_markup=admin_main(lang)
    )
    # Сохраняем message_id для последующего удаления
    menu.last_menu_message[message.chat.id] = msg.message_id


ROLE_HANDLERS = {
    "admin": admin_menu,
    # "specialist": specialist_menu,
    # "client": client_menu,
}


async def route_by_role(event: TelegramObject, lang: str):
    tg_id = event.from_user.id
    role = await get_user_role(tg_id)

    handler = ROLE_HANDLERS.get(role)
    if not handler:
        if isinstance(event, Message):
            await event.answer(f"Role: {role} (menu not implemented)")
        return

    msg: Message = event.message if isinstance(event, CallbackQuery) else event
    await handler(msg, lang)


# ===============================
# REGISTER HANDLERS
# ===============================

dp.include_router(admin_reply.setup(menu))


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
