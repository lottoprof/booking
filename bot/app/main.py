# bot/app/main.py

import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

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


BOT_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

menu = MenuController()

load_messages(BOT_DIR / "i18n" / "messages.txt")


# ===============================
# USER CONTEXT (from gateway)
# ===============================

@dataclass
class TgUserContext:
    """Контекст пользователя от gateway."""
    tg_id: int
    user_id: Optional[int]
    role: str
    is_new: bool


# Временное хранилище контекста для текущего update
# (передаётся из process_update в handlers)
_current_user_context: dict[int, TgUserContext] = {}


def get_user_context(tg_id: int) -> Optional[TgUserContext]:
    """Получить контекст пользователя для текущего запроса."""
    return _current_user_context.get(tg_id)


def get_user_role(tg_id: int) -> str:
    """Получить роль пользователя."""
    ctx = _current_user_context.get(tg_id)
    return ctx.role if ctx else "client"


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
    role = get_user_role(tg_id)

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

dp.include_router(admin_reply.setup(menu, get_user_role))


# ===============================
# GATEWAY ENTRYPOINT
# ===============================

async def process_update(update_data: dict, user_context=None):
    """
    Единственная точка входа для gateway.
    
    Args:
        update_data: Telegram update dict
        user_context: TgUserContext от gateway (аутентификация)
    """
    try:
        update = Update.model_validate(update_data)
    except Exception as e:
        logger.warning("Invalid Telegram update: %s", e)
        return

    # Сохраняем контекст пользователя
    if user_context:
        _current_user_context[user_context.tg_id] = TgUserContext(
            tg_id=user_context.tg_id,
            user_id=user_context.user_id,
            role=user_context.role,
            is_new=user_context.is_new
        )
        logger.info(f"User context: tg_id={user_context.tg_id}, role={user_context.role}")

    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Error while processing Telegram update")
    finally:
        # Очищаем контекст после обработки
        if user_context:
            _current_user_context.pop(user_context.tg_id, None)

