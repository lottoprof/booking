"""
bot/app/main.py

Точка входа Telegram-бота.

ТОЛЬКО:
- Инициализация bot, dp
- process_update для gateway
- route_by_role для первичного входа
- Регистрация handlers

НЕ содержит бизнес-логики меню.
"""

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
from bot.app.utils.state import user_lang
from bot.app.utils.menucontroller import MenuController
from bot.app.flows.admin.menu import AdminMenuFlow
from bot.app.handlers import admin_reply


# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------

BOT_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

menu = MenuController()
admin_flow = AdminMenuFlow(menu)

load_messages(BOT_DIR / "i18n" / "messages.txt")


# ------------------------------------------------------------------
# User context (from gateway)
# ------------------------------------------------------------------

@dataclass
class TgUserContext:
    """Контекст пользователя от gateway."""
    tg_id: int
    user_id: Optional[int]
    role: str
    is_new: bool


_current_user_context: dict[int, TgUserContext] = {}


def get_user_context(tg_id: int) -> Optional[TgUserContext]:
    """Получить контекст пользователя."""
    return _current_user_context.get(tg_id)


def get_user_role(tg_id: int) -> str:
    """Получить роль пользователя."""
    ctx = _current_user_context.get(tg_id)
    return ctx.role if ctx else "client"


# ------------------------------------------------------------------
# Entry points
# ------------------------------------------------------------------

@dp.message(Command("start"))
async def start_handler(message: Message):
    """Обработка /start."""
    tg_id = message.from_user.id
    lang = user_lang.get(tg_id)

    # Выбор языка если не установлен
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
    """Обработка выбора языка."""
    tg_id = callback.from_user.id
    lang = callback.data.split(":", 1)[1]

    user_lang[tg_id] = lang

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.answer()
    await route_by_role(callback, lang)


# ------------------------------------------------------------------
# Role router
# ------------------------------------------------------------------

async def route_by_role(event: TelegramObject, lang: str):
    """Маршрутизация по роли — только первичный вход."""
    tg_id = event.from_user.id
    role = get_user_role(tg_id)

    # Получаем Message из event
    if isinstance(event, CallbackQuery):
        message = event.message
    else:
        message = event

    # Роутинг по роли
    if role == "admin":
        await admin_flow.show_main(message, lang)
    elif role == "specialist":
        # TODO: await specialist_flow.show_main(message, lang)
        await message.answer(f"Role: specialist (not implemented)")
    elif role == "client":
        # TODO: await client_flow.show_main(message, lang)
        await message.answer(f"Role: client (not implemented)")
    else:
        await message.answer(f"Unknown role: {role}")


# ------------------------------------------------------------------
# Register handlers
# ------------------------------------------------------------------

dp.include_router(admin_reply.setup(menu, get_user_role))


# ------------------------------------------------------------------
# Gateway entrypoint
# ------------------------------------------------------------------

async def process_update(update_data: dict, user_context=None):
    """
    Единственная точка входа для gateway.
    """
    try:
        update = Update.model_validate(update_data)
    except Exception as e:
        logger.warning("Invalid Telegram update: %s", e)
        return

    # Сохраняем контекст
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
        logger.exception("Error processing Telegram update")
    finally:
        if user_context:
            _current_user_context.pop(user_context.tg_id, None)

