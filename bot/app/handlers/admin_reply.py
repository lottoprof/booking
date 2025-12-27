"""
bot/app/handlers/admin_reply.py

Роутинг Reply-кнопок админа.

ВАЖНО: FSM роутеры включаются ПЕРВЫМИ для приоритета state handlers.
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.admin.menu import AdminMenuFlow
from bot.app.flows.admin import locations as locations_flow

import logging
logger = logging.getLogger(__name__)

router = Router()


def setup(menu_controller, get_user_role):
    """Настройка роутера."""
    
    flow = AdminMenuFlow(menu_controller)
    
    # Setup locations flow и включаем ПЕРВЫМ (FSM приоритет!)
    loc_router = locations_flow.setup(menu_controller, get_user_role)
    router.include_router(loc_router)

    @router.message()
    async def handle_admin_reply(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        
        # =====================================================
        # ВАЖНО: если есть активный FSM state — пропускаем!
        # FSM handler из loc_router должен был обработать.
        # Если мы тут — значит FSM handler не сработал,
        # но state есть — не мешаем FSM.
        # =====================================================
        current_state = await state.get_state()
        if current_state:
            logger.info(f"Skipping admin_reply, active FSM state: {current_state}")
            return
        
        if get_user_role(tg_id) != "admin":
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)
        text = message.text

        # ==============================================================
        # MAIN MENU → Level 1
        # ==============================================================
        
        if text == t("admin:main:settings", lang):
            await flow.to_settings(message, lang)

        elif text == t("admin:main:schedule", lang):
            await flow.to_schedule(message, lang)

        elif text == t("admin:main:clients", lang):
            await flow.to_clients(message, lang)

        # ==============================================================
        # Level 1 → BACK to Main
        # ==============================================================

        elif text in (
            t("admin:settings:back", lang),
            t("admin:schedule:back", lang),
            t("admin:clients:back", lang),
        ):
            await flow.back_to_main(message, lang)

        # ==============================================================
        # SETTINGS → Level 2
        # ==============================================================

        elif text == t("admin:settings:locations", lang):
            await flow.to_locations(message, lang)

        elif text == t("admin:settings:rooms", lang):
            pass  # TODO

        elif text == t("admin:settings:services", lang):
            pass  # TODO

        elif text == t("admin:settings:packages", lang):
            pass  # TODO

        elif text == t("admin:settings:specialists", lang):
            pass  # TODO

        elif text == t("admin:settings:spec_services", lang):
            pass  # TODO

        # ==============================================================
        # LOCATIONS menu
        # ==============================================================

        elif text == t("admin:locations:list", lang):
            pass  # TODO: show locations list inline

        elif text == t("admin:locations:create", lang):
            await loc_router.start_create(message, state)

        elif text == t("admin:locations:back", lang):
            await flow.back_to_settings(message, lang)

        # ==============================================================
        # SCHEDULE submenu
        # ==============================================================

        elif text == t("admin:schedule:overrides", lang):
            pass  # TODO

        # ==============================================================
        # CLIENTS submenu
        # ==============================================================

        elif text == t("admin:clients:find", lang):
            pass  # TODO

        elif text == t("admin:clients:bookings", lang):
            pass  # TODO

        elif text == t("admin:clients:wallets", lang):
            pass  # TODO

    return router

