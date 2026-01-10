"""
bot/app/handlers/client_reply.py

Роутинг Reply-кнопок клиента.
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.client.menu import ClientMenuFlow

import logging
logger = logging.getLogger(__name__)

# Главный роутер — будет включать sub-роутеры
router = Router(name="client_main")


def setup(menu_controller, get_user_role):
    """Настройка роутера клиента."""
    
    flow = ClientMenuFlow(menu_controller)
    mc = menu_controller

    # Sub-роутер для Reply кнопок (без FSM фильтра)
    reply_router = Router(name="client_reply")

    # ==========================================================
    # CONTEXT HANDLERS: menu_context → {action → handler}
    #
    # Пока у клиента один уровень меню.
    # Заготовка оставлена для масштабирования.
    # ==========================================================
    
    context_handlers = {
        # "some_context": {
        #     "back": lambda msg, st, lang: flow.back_to_main(msg, lang),
        # }
    }

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
        logger.info(f"[CLIENT_REPLY] Processing: lang={lang}")

        # Получаем текущий контекст меню
        menu_ctx = await mc.get_menu_context(chat_id)
        logger.info(f"[CLIENT_REPLY] menu_ctx={menu_ctx}")

        # ==============================================================
        # CONTEXT-AWARE (заготовка)
        # ==============================================================

        if menu_ctx and menu_ctx in context_handlers:
            handlers = context_handlers[menu_ctx]

            for action, handler in handlers.items():
                key = f"client:{menu_ctx}:{action}"

                if text == t(key, lang):
                    if action == "back":
                        await handler(message, state, lang)
                    else:
                        await handler(message, state)
                    return

        # ==============================================================
        # MAIN MENU
        # ==============================================================

        if text == t("client:main:book", lang):
            logger.info("[CLIENT_REPLY] Book service selected")
            # TODO: запустить FSM выбора слота (ClientBooking)
            # TODO: client_booking.start(message, state)
            return

        elif text == t("client:main:bookings", lang):
            logger.info("[CLIENT_REPLY] My bookings selected")
            # TODO: показать список записей (Inline, readonly)
            return

        elif text == t("client:main:services", lang):
            logger.info("[CLIENT_REPLY] Services selected")
            # TODO: показать остаток услуг (Inline, readonly)
            return

        elif text == t("client:main:contact", lang):
            logger.info("[CLIENT_REPLY] Contact selected")
            # TODO: показать контактную информацию / инструкцию
            return

    # =====================================================
    # ПОРЯДОК ВАЖЕН!
    # FSM роутеры клиента (когда появятся) → ПЕРВЫЕ
    # reply_router → ПОСЛЕДНИЙ
    # =====================================================
    router.include_router(reply_router)

    return router

