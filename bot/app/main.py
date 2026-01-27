# bot/app/main.py

import os
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, BaseFilter
from aiogram.types import Update, Message, CallbackQuery, TelegramObject
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.context import FSMContext

from bot.app.config import BOT_TOKEN
from bot.app.i18n.loader import load_messages, t, DEFAULT_LANG
from bot.app.keyboards.common import language_inline
from bot.app.keyboards.admin import admin_main
from bot.app.keyboards.client import client_main
from bot.app.utils.state import user_lang
from bot.app.utils.menucontroller import MenuController
from bot.app.utils.api import api
from bot.app.flows.admin.menu import AdminMenuFlow
from bot.app.flows.client.menu import ClientMenuFlow

from bot.app.handlers import admin_reply
from bot.app.handlers import client_reply
from bot.app.flows.admin import booking_notify
from bot.app.flows.common import booking_edit

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
client_flow = ClientMenuFlow(menu)

load_messages(BOT_DIR / "i18n" / "messages.txt")


# ===============================
# USER CONTEXT (from gateway)
# ===============================

@dataclass
class TgUserContext:
    """Контекст пользователя от gateway."""
    tg_id: int
    user_id: Optional[int]
    company_id: Optional[int]
    role: str
    is_new: bool


_current_user_context: dict[int, TgUserContext] = {}


def get_user_context(tg_id: int) -> Optional[TgUserContext]:
    return _current_user_context.get(tg_id)


def get_user_role(tg_id: int) -> str:
    ctx = _current_user_context.get(tg_id)
    return ctx.role if ctx else "client"


# ===============================
# ROLE FILTER
# ===============================

class RoleFilter(BaseFilter):
    """Фильтр по роли пользователя. Принимает одну или несколько ролей."""

    def __init__(self, *roles: str):
        self.roles = set(roles)

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        tg_id = event.from_user.id
        user_role = get_user_role(tg_id)
        return user_role in self.roles


# ===============================
# USER CREATION (without phone)
# ===============================

async def create_user_without_phone(message: Message) -> Optional[int]:
    """
    Создаёт user без телефона при первом контакте.
    
    Из Telegram доступно: tg_id (всегда), first_name (всегда),
    last_name (опционально), tg_username (опционально).
    """
    user = message.from_user
    
    # Отклоняем ботов
    if user.is_bot:
        logger.warning(f"[REG] Rejected bot: tg_id={user.id}")
        return None
    
    company = await api.get_company()
    if not company:
        logger.error("[REG] No company in database")
        return None
    
    new_user = await api.create_user(
        company_id=company["id"],
        phone=None,
        tg_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        tg_username=user.username,
    )
    
    if not new_user:
        logger.error(f"[REG] Failed to create user for tg_id={user.id}")
        return None
    
    # Назначаем роль client
    await api.create_user_role(new_user["id"], role_id=4)
    
    logger.info(f"[REG] Created user: tg_id={user.id}, user_id={new_user['id']}")
    return new_user["id"]


# ===============================
# ENTRYPOINTS
# ===============================

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработка команды /start."""
    tg_id = message.from_user.id
    chat_id = message.chat.id
    
    logger.info(f"start_handler: tg_id={tg_id}, chat_id={chat_id}")

    # Сброс FSM state
    await state.clear()
    
    # Сброс языка
    user_lang.pop(tg_id, None)
    
    # Сброс навигационного состояния
    await menu.reset(chat_id)
    
    # Проверяем, новый ли пользователь
    ctx = get_user_context(tg_id)
    is_new = ctx.is_new if ctx else False
    
    # Если новый — создаём user без телефона
    if is_new:
        user_id = await create_user_without_phone(message)
        if user_id:
            # Обновляем локальный контекст
            _current_user_context[tg_id] = TgUserContext(
                tg_id=tg_id,
                user_id=user_id,
                company_id=ctx.company_id if ctx else None,
                role="client",
                is_new=False,
            )
        else:
            # Не удалось создать (бот или ошибка БД)
            await message.answer("❌ Registration failed")
            return
    
    # Показываем выбор языка
    kb = language_inline()
    if kb:
        await message.answer("🌐", reply_markup=kb)
        return
    
    # Если языков меньше 2 — используем дефолтный
    lang = DEFAULT_LANG
    user_lang[tg_id] = lang
    
    # Показать меню по роли
    await route_by_role(message, lang)


@dp.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора языка (из inline-кнопок)."""
    tg_id = callback.from_user.id
    chat_id = callback.message.chat.id
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
    
    # Показать меню по роли
    role = get_user_role(tg_id)
    logger.info(f"language_callback: showing menu for role={role}")
    
    await show_menu_for_role(role, chat_id, lang)


# ===============================
# ROLE MENU DISPLAY
# ===============================

async def show_menu_for_role(role: str, chat_id: int, lang: str) -> None:
    """Показать меню для роли (без Message объекта)."""
    if role == "admin":
        await menu.show_for_chat(
            bot=bot,
            chat_id=chat_id,
            kb=admin_main(lang),
            title=t("admin:main:title", lang),
            menu_context=None
        )
    elif role == "specialist":
        await bot.send_message(chat_id, "Role: specialist (menu not implemented)")
    elif role == "client":
        await menu.show_for_chat(
            bot=bot,
            chat_id=chat_id,
            kb=client_main(lang),
            title=t("client:main:title", lang),
            menu_context=None
        )
    else:
        await bot.send_message(chat_id, f"Role: {role} (unknown)")


# ===============================
# ROLE ROUTER (ENTRY ONLY)
# ===============================

async def admin_entry(message: Message, lang: str):
    """Первичный вход в админ-меню."""
    logger.info(f"admin_entry: chat_id={message.chat.id}, lang={lang}")
    await admin_flow.show_main(message, lang)


async def client_entry(message: Message, lang: str):
    """Первичный вход в клиент-меню."""
    logger.info(f"client_entry: chat_id={message.chat.id}, lang={lang}")
    await client_flow.show_main(message, lang)


ROLE_HANDLERS = {
    "admin": admin_entry,
    "client": client_entry,
}


async def route_by_role(event: TelegramObject, lang: str):
    """Маршрутизация по роли (только для Message)."""
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
# REGISTER HANDLERS (с фильтрами ролей)
# ===============================

# Admin роутер — только для role=admin
admin_router = admin_reply.setup(menu, get_user_role)
admin_router.message.filter(RoleFilter("admin"))
admin_router.callback_query.filter(RoleFilter("admin"))
dp.include_router(admin_router)

# Client роутер — только для role=client
client_router = client_reply.setup(menu, get_user_role, get_user_context)
client_router.message.filter(RoleFilter("client"))
client_router.callback_query.filter(RoleFilter("client"))
dp.include_router(client_router)

# Booking notification callbacks — admin + manager
notify_router = booking_notify.router
notify_router.callback_query.filter(RoleFilter("admin", "manager"))
dp.include_router(notify_router)

# Client reminder callbacks (bkr:*)
client_notify_router = booking_notify.client_notify_router
client_notify_router.callback_query.filter(RoleFilter("client"))
dp.include_router(client_notify_router)

# Booking edit module — all roles (bke:* callbacks)
dp.include_router(booking_edit.router)


# ===============================
# GATEWAY ENTRYPOINT
# ===============================

async def process_update(update_data: dict, user_context=None):
    """Точка входа для обработки Telegram update от gateway."""
    try:
        update = Update.model_validate(update_data)
    except Exception as e:
        logger.warning("Invalid Telegram update: %s", e)
        return

    if user_context:
        _current_user_context[user_context.tg_id] = TgUserContext(
            tg_id=user_context.tg_id,
            user_id=user_context.user_id,
            company_id=user_context.company_id,
            role=user_context.role,
            is_new=user_context.is_new
        )
        logger.info(f"User context: tg_id={user_context.tg_id}, role={user_context.role}, is_new={user_context.is_new}")

    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Error while processing Telegram update")
    finally:
        if user_context:
            _current_user_context.pop(user_context.tg_id, None)

