"""
bot/app/handlers/client_reply.py

Роутинг Reply-кнопок клиента + PhoneGate.
"""

from aiogram import Router, F
from aiogram.types import Message, ContentType
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.client.menu import ClientMenuFlow
from bot.app.utils.phone_utils import (
    PhoneGate,
    phone_required,
    show_phone_request,
    save_user_phone,
    validate_contact,
)

import logging
logger = logging.getLogger(__name__)

router = Router(name="client_main")


def setup(menu_controller, get_user_role, get_user_context):
    """Настройка роутера клиента."""
    
    flow = ClientMenuFlow(menu_controller)
    mc = menu_controller

    # FSM роутер для PhoneGate (ПЕРВЫЙ)
    fsm_router = Router(name="client_fsm")
    
    # Reply роутер (ПОСЛЕДНИЙ)
    reply_router = Router(name="client_reply")

    # ==========================================================
    # PHONE GATE FSM
    # ==========================================================

    @fsm_router.message(PhoneGate.waiting, F.content_type == ContentType.CONTACT)
    async def handle_phone_contact(message: Message, state: FSMContext):
        """Обработка контакта в PhoneGate."""
        tg_id = message.from_user.id
        data = await state.get_data()
        lang = data.get("lang", DEFAULT_LANG)
        next_action = data.get("next_action")
        
        logger.info(f"[PHONE_GATE] Contact received: tg_id={tg_id}, next_action={next_action}")
        
        # Валидация контакта
        valid, phone = validate_contact(message.contact, tg_id)
        if not valid:
            await message.answer(t("registration:error", lang))
            return
        
        # Получаем user_id
        ctx = get_user_context(tg_id)
        if not ctx or not ctx.user_id:
            logger.error(f"[PHONE_GATE] No user context for tg_id={tg_id}")
            await message.answer(t("registration:error", lang))
            await state.clear()
            return
        
        # Сохраняем телефон (+ matching с imported_clients)
        success, error_key = await save_user_phone(ctx.user_id, phone)
        if not success:
            await message.answer(t(error_key, lang))
            return
        
        # Очищаем FSM
        await state.clear()
        
        # Уведомление
        await message.answer(t("registration:complete", lang))
        
        # Продолжаем действие
        if next_action == "book":
            await do_book(message, state, lang)
        elif next_action == "bookings":
            await do_bookings(message, state, lang)
        elif next_action == "contact":
            await do_contact(message, state, lang)
        else:
            # Возврат в главное меню
            await flow.show_main(message, lang)

    # ==========================================================
    # ACTION HANDLERS
    # ==========================================================

    async def do_book(message: Message, state: FSMContext, lang: str):
        """Запуск booking flow."""
        logger.info("[CLIENT] Starting book flow")
        # TODO: запустить FSM выбора слота (ClientBooking)
        await message.answer("📝 Booking flow (not implemented)")

    async def do_bookings(message: Message, state: FSMContext, lang: str):
        """Показ списка записей."""
        logger.info("[CLIENT] Showing bookings")
        # TODO: показать список записей
        await message.answer("📋 My bookings (not implemented)")

    async def do_contact(message: Message, state: FSMContext, lang: str):
        """Показ контактной информации."""
        logger.info("[CLIENT] Showing contact")
        # TODO: показать контакты
        await message.answer("📞 Contact info (not implemented)")

    # ==========================================================
    # PHONE GATE TRIGGER
    # ==========================================================

    async def require_phone_and_do(
        message: Message,
        state: FSMContext,
        lang: str,
        action: str,
        action_handler
    ):
        """
        Проверяет наличие телефона, запрашивает если нет.
        
        Args:
            action: "book" | "bookings" | "contact"
            action_handler: функция для выполнения если телефон есть
        """
        tg_id = message.from_user.id
        ctx = get_user_context(tg_id)
        
        if not ctx or not ctx.user_id:
            logger.error(f"[PHONE_GATE] No user context: tg_id={tg_id}")
            await message.answer(t("registration:error", lang))
            return
        
        # Проверяем телефон
        if await phone_required(ctx.user_id):
            logger.info(f"[PHONE_GATE] Phone required for action={action}")
            await state.set_state(PhoneGate.waiting)
            await state.update_data(next_action=action, lang=lang)
            await show_phone_request(mc, message, lang)
            return
        
        # Телефон есть — выполняем действие
        await action_handler(message, state, lang)

    # ==========================================================
    # REPLY HANDLERS
    # ==========================================================

    @reply_router.message()
    async def handle_client_reply(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text

        logger.info(f"[CLIENT_REPLY] Received: tg_id={tg_id}, text='{text}'")

        # Если есть активный FSM state — не обрабатываем
        current_state = await state.get_state()
        if current_state:
            logger.info(f"[CLIENT_REPLY] Skipped, FSM active: {current_state}")
            return

        role = get_user_role(tg_id)
        if role != "client":
            logger.info(f"[CLIENT_REPLY] Skipped, role={role}")
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)

        # ==============================================================
        # MAIN MENU (с phone gate)
        # ==============================================================

        if text == t("client:main:book", lang):
            await require_phone_and_do(message, state, lang, "book", do_book)
            return

        elif text == t("client:main:bookings", lang):
            await require_phone_and_do(message, state, lang, "bookings", do_bookings)
            return

        elif text == t("client:main:contact", lang):
            await require_phone_and_do(message, state, lang, "contact", do_contact)
            return

        elif text == t("client:main:services", lang):
            logger.info("[CLIENT_REPLY] Services selected")
            # Услуги — без phone gate (просто просмотр)
            await message.answer("📋 Services (not implemented)")
            return

    # =====================================================
    # ПОРЯДОК: FSM → Reply
    # =====================================================
    router.include_router(fsm_router)
    router.include_router(reply_router)

    return router

