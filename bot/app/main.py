import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

from app.config import BOT_TOKEN
from app.i18n.loader import load_messages, t, DEFAULT_LANG
from app.keyboards.common import language_inline
from app.utils.state import user_lang

from app.flows.admin.menu import admin_menu
from app.flows.specialist.menu import specialist_menu
from app.flows.client.menu import client_menu

from app.auth import get_user_role


# ===============================
# LOGGING
# ===============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===============================
# BOT CORE (library mode)
# ===============================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Загружаем переводы ОДИН РАЗ при импорте
load_messages("app/i18n/messages.txt")


# ===============================
# HANDLERS
# ===============================

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    tg_id = message.from_user.id

    # 1. Проверяем выбран ли язык
    lang = user_lang.get(tg_id)

    if not lang:
        kb = language_inline()

        # если языков больше одного — спрашиваем
        if kb:
            await message.answer(
                t("common:lang:choose", DEFAULT_LANG),
                reply_markup=kb
            )
            return

        # если язык один — выбираем автоматически
        lang = DEFAULT_LANG
        user_lang[tg_id] = lang

    # 2. Передаём управление маршрутизатору
    await route_by_role(message, lang)


@dp.callback_query_handler(lambda c: c.data.startswith("lang:"))
async def language_callback(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    lang = callback.data.split(":", 1)[1]

    user_lang[tg_id] = lang

    # inline одноразовый
    await callback.message.delete()
    await callback.answer()

    await route_by_role(callback.message, lang)


# ===============================
# ROUTER
# ===============================

async def route_by_role(message: types.Message, lang: str):
    """
    Единая точка маршрутизации.
    Роль определяется backend'ом.
    """
    role = await get_user_role(message.from_user.id)

    if role == "admin":
        await admin_menu(message, lang)
        return

    if role == "specialist":
        await specialist_menu(message, lang)
        return

    # default = client
    await client_menu(message, lang)


# ===============================
# GATEWAY ENTRYPOINT
# ===============================

async def process_update(update_data: dict):
    """
    Единственная точка входа для gateway.
    Gateway передаёт сюда Telegram Update как dict.
    """
    try:
        update = Update(**update_data)
    except Exception as e:
        logger.warning("Invalid Telegram update: %s", e)
        return

    try:
        await dp.process_update(update)
    except Exception:
        logger.exception("Error while processing Telegram update")


