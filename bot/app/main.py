# bot/app/main.py

import os
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Update, Message, CallbackQuery, TelegramObject, ContentType
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.config import BOT_TOKEN
from bot.app.i18n.loader import load_messages, t, DEFAULT_LANG
from bot.app.keyboards.common import language_inline, request_phone_keyboard
from bot.app.keyboards.admin import admin_main
from bot.app.utils.state import user_lang
from bot.app.utils.menucontroller import MenuController
from bot.app.utils.api import api
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
# REGISTRATION FSM
# ===============================

class Registration(StatesGroup):
    """Состояния регистрации."""
    phone = State()


# ===============================
# ENTRYPOINTS
# ===============================

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработка команды /start."""
    tg_id = message.from_user.id
    chat_id = message.chat.id
    
    logger.info(f"start_handler: tg_id={tg_id}, chat_id={chat_id}")

    # Сброс FSM state (очистка застрявших состояний)
    await state.clear()
    
    # Сброс языка — пользователь начинает заново
    user_lang.pop(tg_id, None)
    
    # Сброс навигационного состояния
    await menu.reset(chat_id)
    
    # Проверяем, нужна ли регистрация
    ctx = get_user_context(tg_id)
    is_new = ctx.is_new if ctx else False
    
    logger.info(f"start_handler: is_new={is_new}")
    
    # Показываем выбор языка
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
    
    # Если новый пользователь — запускаем регистрацию
    if is_new:
        await start_registration(message, state, lang)
        return
    
    # Показать меню по роли (Message доступен)
    await route_by_role(message, lang)


@dp.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery, state: FSMContext):
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
    
    # Проверяем, нужна ли регистрация
    ctx = get_user_context(tg_id)
    is_new = ctx.is_new if ctx else False
    
    logger.info(f"language_callback: is_new={is_new}")
    
    # Если новый пользователь — запускаем регистрацию
    if is_new:
        await start_registration_for_chat(chat_id, state, lang, tg_id)
        return
    
    # Показать меню по роли (используем show_for_chat, т.к. Message удалён)
    role = get_user_role(tg_id)
    logger.info(f"language_callback: showing menu for role={role}")
    
    await show_menu_for_role(role, chat_id, lang)


# ===============================
# REGISTRATION FLOW
# ===============================

async def start_registration(message: Message, state: FSMContext, lang: str):
    """Начинает регистрацию (с Message объектом)."""
    tg_id = message.from_user.id
    
    logger.info(f"[REG] Starting registration for tg_id={tg_id}")
    
    await state.update_data(lang=lang)
    await state.set_state(Registration.phone)
    
    text = t("registration:welcome", lang)
    kb = request_phone_keyboard(lang)
    
    await menu.show(message, kb, title=text)


async def start_registration_for_chat(chat_id: int, state: FSMContext, lang: str, tg_id: int):
    """Начинает регистрацию (без Message объекта, после language_callback)."""
    logger.info(f"[REG] Starting registration for tg_id={tg_id} (from callback)")
    
    await state.update_data(lang=lang)
    await state.set_state(Registration.phone)
    
    text = t("registration:welcome", lang)
    kb = request_phone_keyboard(lang)
    
    await menu.show_for_chat(
        bot=bot,
        chat_id=chat_id,
        kb=kb,
        title=text,
        menu_context=None
    )


@dp.message(Registration.phone, F.content_type == ContentType.CONTACT)
async def process_contact(message: Message, state: FSMContext):
    """Обработка полученного контакта."""
    tg_id = message.from_user.id
    chat_id = message.chat.id
    data = await state.get_data()
    lang = data.get("lang") or user_lang.get(tg_id, DEFAULT_LANG)
    
    contact = message.contact
    
    # Проверяем, что контакт принадлежит пользователю
    if contact.user_id != tg_id:
        logger.warning(f"[REG] Contact user_id mismatch: {contact.user_id} != {tg_id}")
        await message.answer(t("registration:error", lang))
        return
    
    phone = contact.phone_number
    if not phone:
        await message.answer(t("registration:error", lang))
        return
    
    logger.info(f"[REG] Contact received: tg_id={tg_id}, phone={phone}")
    
    # Ищем пользователя по телефону
    user, found = await api.get_user_by_phone(phone)
    
    ctx = get_user_context(tg_id)
    user_info = {
        "tg_id": tg_id,
        "tg_username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
    }
    
    if found and user:
        # Пользователь найден по телефону
        if not user.get("is_active", True):
            # Деактивирован
            logger.info(f"[REG] User deactivated: phone={phone}")
            await state.clear()
            await message.answer(t("registration:deactivated", lang))
            return
        
        # Связываем tg_id с существующим пользователем (перезапись)
        logger.info(f"[REG] Linking tg_id={tg_id} to existing user_id={user['id']}")
        result = await api.update_user(
            user["id"],
            tg_id=tg_id,
            tg_username=user_info.get("tg_username"),
        )
        if not result:
            await message.answer(t("registration:error", lang))
            return
        
        user_id = user["id"]
        company_id = user.get("company_id")
        role = "client"  # TODO: получить реальную роль
        
    elif not found:
        # Пользователь не найден — создаём нового
        company = await api.get_company()
        if not company:
            logger.error("[REG] No company in database")
            await message.answer(t("registration:error", lang))
            return
        
        logger.info(f"[REG] Creating new user: phone={phone}, tg_id={tg_id}")
        new_user = await api.create_user(
            company_id=company["id"],
            phone=phone,
            tg_id=tg_id,
            tg_username=user_info.get("tg_username"),
            first_name=user_info.get("first_name"),
            last_name=user_info.get("last_name"),
        )
        
        if not new_user:
            await message.answer(t("registration:error", lang))
            return
        
        # Назначаем роль client
        await api.create_user_role(new_user["id"], role_id=4)
        
        user_id = new_user["id"]
        company_id = company["id"]
        role = "client"
        
    else:
        # Ошибка API
        await message.answer(t("registration:error", lang))
        return
    
    # Очищаем FSM
    await state.clear()
    
    # Обновляем локальный контекст
    _current_user_context[tg_id] = TgUserContext(
        tg_id=tg_id,
        user_id=user_id,
        company_id=company_id,
        role=role,
        is_new=False,
    )
    
    logger.info(f"[REG] Registration complete: tg_id={tg_id}, user_id={user_id}")
    
    # Сбрасываем меню
    await menu.reset(chat_id)
    
    # Показываем сообщение и меню
    await message.answer(t("registration:complete", lang))
    await route_by_role(message, lang)


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

