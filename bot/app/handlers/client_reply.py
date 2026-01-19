# bot/app/handlers/client_reply.py
"""
Reply-кнопки клиента + Booking Flow.

PhoneGate роутер в phone_gate.py — подключается отдельно в main.py.
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.client.menu import ClientMenuFlow
from bot.app.utils.phone_utils import (
    PhoneGate,
    phone_required,
    show_phone_request,
)
from bot.app.handlers.phone_gate import register_phone_callback
from bot.app.flows.client.booking import setup as setup_booking

import logging
logger = logging.getLogger(__name__)

router = Router(name="client_main")


def setup(menu_controller, get_user_role, get_user_context):
    """Настройка роутера клиента."""
    
    flow = ClientMenuFlow(menu_controller)
    mc = menu_controller

    # Booking роутер
    booking_router = setup_booking(menu_controller, get_user_context)
    
    # Reply роутер
    reply_router = Router(name="client_reply")

    # ==========================================================
    # ACTION HANDLERS
    # ==========================================================

    async def do_book(message: Message, state: FSMContext, lang: str, user_id: int):
        """Запуск booking flow."""
        logger.info(f"[CLIENT] do_book user_id={user_id}")
        await booking_router.start_booking(message, state, lang, user_id)

    async def do_bookings(message: Message, state: FSMContext, lang: str, user_id: int):
        """Список записей."""
        logger.info(f"[CLIENT] do_bookings user_id={user_id}")
        await message.answer("📋 Мои записи (в разработке)")

    async def do_contact(message: Message, state: FSMContext, lang: str, user_id: int):
        """Контакты."""
        logger.info("[CLIENT] do_contact")
        await message.answer("📞 Контакты (в разработке)")

    # ==========================================================
    # PHONE GATE CALLBACKS
    # ==========================================================

    async def on_phone_book(message, state, lang, user_id, data):
        await do_book(message, state, lang, user_id)

    async def on_phone_bookings(message, state, lang, user_id, data):
        await do_bookings(message, state, lang, user_id)

    async def on_phone_contact(message, state, lang, user_id, data):
        await do_contact(message, state, lang, user_id)

    register_phone_callback("book", on_phone_book)
    register_phone_callback("bookings", on_phone_bookings)
    register_phone_callback("contact", on_phone_contact)

    # ==========================================================
    # REQUIRE PHONE
    # ==========================================================

    async def require_phone_and_do(
        message: Message,
        state: FSMContext,
        lang: str,
        action: str,
        do_action
    ):
        """Проверяет телефон, запрашивает если нет."""
        tg_id = message.from_user.id
        ctx = get_user_context(tg_id)
        
        if not ctx or not ctx.user_id:
            await message.answer(t("registration:error", lang))
            return
        
        user_id = ctx.user_id
        
        if await phone_required(user_id):
            # Устанавливаем FSM + показываем клавиатуру
            await state.set_state(PhoneGate.waiting)
            await state.update_data(next_action=action, lang=lang)
            await show_phone_request(mc, message, lang)
            return
        
        # Телефон есть
        await do_action(message, state, lang, user_id)

    # ==========================================================
    # REPLY HANDLERS
    # ==========================================================

    @reply_router.message()
    async def handle_client_reply(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        text = message.text

        # FSM активен — пропускаем
        current_state = await state.get_state()
        if current_state:
            return

        role = get_user_role(tg_id)
        if role != "client":
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)

        if text == t("client:main:book", lang):
            await require_phone_and_do(message, state, lang, "book", do_book)

        elif text == t("client:main:bookings", lang):
            await require_phone_and_do(message, state, lang, "bookings", do_bookings)

        elif text == t("client:main:contact", lang):
            await require_phone_and_do(message, state, lang, "contact", do_contact)

        elif text == t("client:main:services", lang):
            await message.answer("📋 Услуги (в разработке)")

    # Порядок роутеров
    router.include_router(booking_router)
    router.include_router(reply_router)

    return router

