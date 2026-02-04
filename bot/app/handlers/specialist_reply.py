"""
bot/app/handlers/specialist_reply.py

Routing for specialist Reply buttons.
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.specialist.menu import SpecialistMenuFlow
from bot.app.flows.specialist import google_calendar as gcal_flow

import logging
logger = logging.getLogger(__name__)

router = Router(name="specialist_main")


def setup(menu_controller, get_user_role):
    """Setup specialist router."""

    flow = SpecialistMenuFlow(menu_controller)
    mc = menu_controller

    # Sub-routers
    reply_router = Router(name="specialist_reply")

    # FSM routers
    gcal_router = gcal_flow.setup(menu_controller, get_user_role)

    # Context handlers
    context_handlers = {
        "gcal": {
            "status": lambda msg, st: gcal_router.show_status(msg),
            "back": lambda msg, st, lang: flow.back_to_main(msg, lang),
        },
    }

    @reply_router.message()
    async def handle_specialist_reply(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text

        logger.info(f"[SPECIALIST_REPLY] Received: tg_id={tg_id}, text='{text}'")

        role = get_user_role(tg_id)
        if role != "specialist":
            logger.info(f"[SPECIALIST_REPLY] Skipped, role={role}")
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)
        logger.info(f"[SPECIALIST_REPLY] Processing: lang={lang}")

        # Collect all menu buttons
        menu_buttons = [
            # Main menu
            t("specialist:main:schedule", lang),
            t("specialist:main:gcal", lang),
            # Google Calendar submenu
            t("specialist:gcal:status", lang),
            t("specialist:gcal:back", lang),
        ]

        # Add context-aware buttons
        menu_ctx = await mc.get_menu_context(chat_id)
        if menu_ctx and menu_ctx in context_handlers:
            for action in context_handlers[menu_ctx]:
                menu_buttons.append(t(f"specialist:{menu_ctx}:{action}", lang))

        # If not a menu button — skip (FSM will handle)
        if text not in menu_buttons:
            return

        # Clear FSM if active
        current_state = await state.get_state()
        if current_state:
            logger.info(f"[SPECIALIST_REPLY] Clearing FSM state: {current_state}")
            await state.clear()

        # ==============================================================
        # CONTEXT-AWARE: check by current context
        # ==============================================================

        if menu_ctx and menu_ctx in context_handlers:
            handlers = context_handlers[menu_ctx]

            for action, handler in handlers.items():
                key = f"specialist:{menu_ctx}:{action}"

                if text == t(key, lang):
                    if action == "back":
                        await handler(message, state, lang)
                    else:
                        await handler(message, state)
                    return

        # ==============================================================
        # MAIN MENU → Level 1
        # ==============================================================

        if text == t("specialist:main:schedule", lang):
            # TODO: Implement schedule view for specialists
            await message.answer(t("specialist:schedule:coming_soon", lang))

        elif text == t("specialist:main:gcal", lang):
            await flow.to_gcal(message, lang)

    # Router order: FSM routers first, reply router last
    router.include_router(gcal_router)
    router.include_router(reply_router)

    return router
