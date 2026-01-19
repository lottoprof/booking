# bot/app/handlers/client_reply.py
"""
Reply-кнопки клиента + Booking Flow.

Phone Gate вызывается в booking flow перед подтверждением,
НЕ при нажатии кнопки "Записаться".
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.client.menu import ClientMenuFlow
from bot.app.flows.client.booking import setup as setup_booking

import logging
logger = logging.getLogger(__name__)

router = Router(name="client_main")


def setup(menu_controller, get_user_role, get_user_context):
    """Настройка роутера клиента."""
    
    flow = ClientMenuFlow(menu_controller)
    mc = menu_controller

    # Booking роутер (phone gate внутри, перед confirm)
    booking_router = setup_booking(menu_controller, get_user_context)
    
    # Reply роутер
    reply_router = Router(name="client_reply")

    # ==========================================================
    # REPLY HANDLERS
    # ==========================================================

    @reply_router.message()
    async def handle_client_reply(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        text = message.text

        logger.info(f"[CLIENT_REPLY] Received: tg_id={tg_id}, text='{text}'")

        # FSM активен — пропускаем
        current_state = await state.get_state()
        if current_state:
            logger.info(f"[CLIENT_REPLY] Skipped, FSM active: {current_state}")
            return

        role = get_user_role(tg_id)
        if role != "client":
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)
        ctx = get_user_context(tg_id)
        user_id = ctx.user_id if ctx else None

        # 📅 Записаться — сразу в booking flow (phone gate в конце)
        if text == t("client:main:book", lang):
            if not user_id:
                await message.answer(t("registration:error", lang))
                return
            await booking_router.start_booking(message, state, lang, user_id)

        # 📖 Мои записи
        elif text == t("client:main:bookings", lang):
            logger.info(f"[CLIENT] do_bookings user_id={user_id}")
            await message.answer("📋 Мои записи (в разработке)")

        # 💬 Связаться с нами
        elif text == t("client:main:contact", lang):
            logger.info("[CLIENT] do_contact")
            await message.answer("📞 Контакты (в разработке)")

        # 📋 Услуги
        elif text == t("client:main:services", lang):
            logger.info("[CLIENT] services")
            await message.answer("📋 Услуги (в разработке)")

    # Порядок роутеров
    router.include_router(booking_router)
    router.include_router(reply_router)

    return router

