# bot/app/main.py

import os
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Update, Message, CallbackQuery, TelegramObject
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.context import FSMContext

from bot.app.config import BOT_TOKEN
from bot.app.i18n.loader import load_messages, t, DEFAULT_LANG
from bot.app.keyboards.common import language_inline
from bot.app.keyboards.admin import admin_main
from bot.app.utils.state import user_lang
from bot.app.utils.menucontroller import MenuController
from bot.app.flows.admin.menu import AdminMenuFlow

from bot.app.handlers import admin_reply


BOT_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===============================
# REDIS FSM STORAGE
# ===============================

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set")

storage = RedisStorage.from_url(REDIS_URL)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

menu = MenuController()
admin_flow = AdminMenuFlow(menu)

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


_current_user_context: dict[int, TgUserContext] = {}


def get_user_context(tg_id: int) -> Optional[TgUserContext]:
    return _current_user_context.get(tg_id)


def get_user_role(tg_id: int) -> str:
    ctx = _current_user_context.get(tg_id)
    return ctx.role if ctx else "client"


# ===============================
# ENTRYPOINTS
# ===============================

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработка команды /start."""
    tg_id = message.from_user.id
    chat_id = message.chat.id
    lang = user_lang.get(tg_id)
    
    logger.info(f"start_handler: tg_id={tg_id}, chat_id={chat_id}, lang={lang}")

    # Сброс FSM state (очистка застрявших состояний)
    await state.clear()
    
    # Если язык не выбран — показываем выбор языка
    if not lang:
        kb = language_inline()
        if kb:
            await message.answer(
                t("common:lang:choose", DEFAULT_LANG),
                reply_markup=kb
            )
            return
        # Если языков меньше 2 — используем дефолтный
        lang = DEFAULT_LANG
        user_lang[tg_id] = lang
    
    # Сброс навигационного состояния
    await menu.reset(chat_id)
    
    # Показать меню по роли (Message доступен)
    await route_by_role(message, lang)


@dp.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery):
    """Обработка выбора языка (из inline-кнопок)."""
    tg_id = callback.from_user.id
    chat_id = callback.message.chat.id  # Сохраняем ДО удаления
    lang = callback.data.split(":", 1)[1]
    
    logger.info(f"language_callback: tg_id={tg_id}, chat_id={chat_id}, lang={lang}")

    # Сохраняем язык
    user_lang[tg_id] = lang

    # Удаляем сообщение с выбором языка
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.answer()
    
    # Сброс навигационного состояния
    await menu.reset(chat_id)
    
    # Показать меню по роли (используем show_for_chat, т.к. Message удалён)
    role = get_user_role(tg_id)
    logger.info(f"language_callback: showing menu for role={role}")
    
    await show_menu_for_role(role, chat_id, lang)


# ===============================
# ROLE MENU DISPLAY
# ===============================

async def show_menu_for_role(role: str, chat_id: int, lang: str) -> None:
    """
    Показать меню для роли напрямую (без Message объекта).
    Используется после language_callback.
    """
    if role == "admin":
        await menu.show_for_chat(
            bot=bot,
            chat_id=chat_id,
            kb=admin_main(lang),
            title=t("admin:main:title", lang),
            menu_context=None
        )
    elif role == "specialist":
        # TODO: specialist menu
        await bot.send_message(chat_id, f"Role: specialist (menu not implemented)")
    elif role == "client":
        # TODO: client menu
        await bot.send_message(chat_id, f"Role: client (menu not implemented)")
    else:
        await bot.send_message(chat_id, f"Role: {role} (unknown)")


# ===============================
# ROLE ROUTER (ENTRY ONLY)
# ===============================

async def admin_entry(message: Message, lang: str):
    """Первичный вход в админ-меню."""
    logger.info(f"admin_entry: chat_id={message.chat.id}, lang={lang}")
    await admin_flow.show_main(message, lang)


ROLE_HANDLERS = {
    "admin": admin_entry,
    # "specialist": specialist_entry,
    # "client": client_entry,
}


async def route_by_role(event: TelegramObject, lang: str):
    """
    Маршрутизация по роли.
    
    Используется ТОЛЬКО когда есть валидный Message объект.
    Для CallbackQuery используйте show_menu_for_role() напрямую.
    """
    if not isinstance(event, Message):
        logger.warning(f"route_by_role called with non-Message: {type(event)}")
        return
        
    tg_id = event.from_user.id
    role = get_user_role(tg_id)
    
    logger.info(f"route_by_role: tg_id={tg_id}, role={role}")

    handler = ROLE_HANDLERS.get(role)
    if not handler:
        logger.warning(f"No handler for role: {role}")
        await event.answer(f"Role: {role} (menu not implemented)")
        return

    await handler(event, lang)


# ===============================
# REGISTER HANDLERS
# ===============================

dp.include_router(admin_reply.setup(menu, get_user_role))


# ===============================
# GATEWAY ENTRYPOINT
# ===============================

async def process_update(update_data: dict, user_context=None):
    """Точка входа для обработки Telegram update от gateway."""
    try:
        update = Update.model_validate(update_data)
        logger.info(f"Update parsed: message={update.message is not None}, text={update.message.text if update.message else None}")
    except Exception as e:
        logger.warning("Invalid Telegram update: %s", e)
        return

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
        if user_context:
            _current_user_context.pop(user_context.tg_id, None)

