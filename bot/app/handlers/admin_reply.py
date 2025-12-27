"""
bot/app/handlers/admin_reply.py

Роутинг Reply-кнопок админа.
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.admin.menu import AdminMenuFlow
from bot.app.flows.admin import locations as locations_flow
from bot.app.flows.admin import services as services_flow

import logging
logger = logging.getLogger(__name__)

# Главный роутер — будет включать sub-роутеры
router = Router(name="admin_main")


def setup(menu_controller, get_user_role):
    """Настройка роутера."""
    
    flow = AdminMenuFlow(menu_controller)
    
    # Sub-роутер для Reply кнопок (без FSM фильтра)
    reply_router = Router(name="admin_reply")
    
    # FSM роутеры
    loc_router = locations_flow.setup(menu_controller, get_user_role)
    svc_router = services_flow.setup(menu_controller, get_user_role)

    @reply_router.message()
    async def handle_admin_reply(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        
        # Если есть активный FSM state — не обрабатываем
        current_state = await state.get_state()
        if current_state:
            logger.debug(f"admin_reply skipped, FSM active: {current_state}")
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
            await flow.to_services(message, lang)

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
            await loc_router.show_list(message)

        elif text == t("admin:locations:create", lang):
            await loc_router.start_create(message, state)

        elif text == t("admin:locations:back", lang):
            await flow.back_to_settings(message, lang)

        # ==============================================================
        # SERVICES menu
        # ==============================================================

        elif text == t("admin:services:list", lang):
            await svc_router.show_list(message)

        elif text == t("admin:services:create", lang):
            await svc_router.start_create(message, state)

        elif text == t("admin:services:back", lang):
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

    # =====================================================
    # ПОРЯДОК ВАЖЕН! FSM роутеры ПЕРВЫЕ, reply ПОСЛЕДНИЙ
    # =====================================================
    router.include_router(loc_router)      # FSM handlers
    router.include_router(svc_router)      # FSM handlers  
    router.include_router(reply_router)    # Catch-all последний

    return router

