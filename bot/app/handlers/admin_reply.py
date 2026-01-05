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
from bot.app.flows.admin import rooms as rooms_flow
from bot.app.flows.admin import specialists as specialists_flow
from bot.app.flows.admin import packages as packages_flow


import logging
logger = logging.getLogger(__name__)

# Главный роутер — будет включать sub-роутеры
router = Router(name="admin_main")


def setup(menu_controller, get_user_role):
    """Настройка роутера."""
    
    flow = AdminMenuFlow(menu_controller)
    mc = menu_controller
    
    # Sub-роутер для Reply кнопок (без FSM фильтра)
    reply_router = Router(name="admin_reply")
    
    # FSM роутеры
    loc_router = locations_flow.setup(menu_controller, get_user_role)
    svc_router = services_flow.setup(menu_controller, get_user_role)
    pkg_router, pkg_edit_router = packages_flow.setup(menu_controller, get_user_role)
    room_router = rooms_flow.setup(menu_controller, get_user_role)
    spec_router = specialists_flow.setup(menu_controller, get_user_role)

    # ==========================================================
    # CONTEXT HANDLERS: menu_context → {action → handler}
    # 
    # Ключи i18n: admin:{context}:{action}
    # Пример: admin:locations:list, admin:services:create
    #
    # handler(msg, state) — для обычных действий
    # handler(msg, state, lang) — для back (нужен lang)
    # ==========================================================
    
    context_handlers = {
        "locations": {
            "list": lambda msg, st: loc_router.show_list(msg),
            "create": lambda msg, st: loc_router.start_create(msg, st),
            "back": lambda msg, st, lang: flow.back_to_settings(msg, lang),
        },
        "services": {
            "list": lambda msg, st: svc_router.show_list(msg),
            "create": lambda msg, st: svc_router.start_create(msg, st),
            "back": lambda msg, st, lang: flow.back_to_settings(msg, lang),
        },
        "packages": {
            "list": lambda msg, st: pkg_router.show_list(msg),
            "create": lambda msg, st: pkg_router.start_create(msg, st),
            "back": lambda msg, st, lang: flow.back_to_settings(msg, lang),
        },
        "rooms": {
            "list": lambda msg, st: room_router.show_list(msg),
            "create": lambda msg, st: room_router.start_create(msg, st),
            "back": lambda msg, st, lang: flow.back_to_settings(msg, lang),
        },
        "specialists": {
            "list": lambda msg, st: spec_router.show_list(msg),
            "create": lambda msg, st: spec_router.start_create(msg, st),
            "back": lambda msg, st, lang: flow.back_to_settings(msg, lang),
        },
        "schedule": {
            # "overrides": lambda msg, st: ...,  # TODO
            "back": lambda msg, st, lang: flow.back_to_main(msg, lang),
        },
        "clients": {
            # "find": lambda msg, st: ...,       # TODO
            # "bookings": lambda msg, st: ...,   # TODO
            # "wallets": lambda msg, st: ...,    # TODO
            "back": lambda msg, st, lang: flow.back_to_main(msg, lang),
        },
    }

    @reply_router.message()
    async def handle_admin_reply(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text
        
        logger.info(f"[ADMIN_REPLY] Received: tg_id={tg_id}, text='{text}'")
        
        # Если есть активный FSM state — не обрабатываем
        current_state = await state.get_state()
        if current_state:
            logger.info(f"[ADMIN_REPLY] Skipped, FSM active: {current_state}")
            return
        
        role = get_user_role(tg_id)
        if role != "admin":
            logger.info(f"[ADMIN_REPLY] Skipped, role={role}")
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)
        logger.info(f"[ADMIN_REPLY] Processing: lang={lang}")
        
        # Получаем текущий контекст меню
        menu_ctx = await mc.get_menu_context(chat_id)
        logger.info(f"[ADMIN_REPLY] menu_ctx={menu_ctx}")

        # ==============================================================
        # CONTEXT-AWARE: проверяем по текущему контексту
        # ==============================================================
        
        if menu_ctx and menu_ctx in context_handlers:
            handlers = context_handlers[menu_ctx]
            
            for action, handler in handlers.items():
                key = f"admin:{menu_ctx}:{action}"
                
                if text == t(key, lang):
                    if action == "back":
                        await handler(message, state, lang)
                    else:
                        await handler(message, state)
                    return

        # ==============================================================
        # MAIN MENU → Level 1
        # ==============================================================
        
        expected_settings = t("admin:main:settings", lang)
        logger.info(f"[ADMIN_REPLY] Comparing: text='{text}' vs expected='{expected_settings}'")
        
        if text == t("admin:main:settings", lang):
            logger.info(f"[ADMIN_REPLY] Match! Going to settings")
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
            await flow.to_rooms(message, lang)

        elif text == t("admin:settings:services", lang):
            await flow.to_services(message, lang)

        elif text == t("admin:settings:packages", lang):
            await flow.to_packages(message, lang)

        elif text == t("admin:settings:specialists", lang):
            await flow.to_specialists(message, lang)

    # =====================================================
    # ПОРЯДОК ВАЖЕН! FSM роутеры ПЕРВЫЕ, reply ПОСЛЕДНИЙ
    # =====================================================
    router.include_router(loc_router)
    router.include_router(svc_router)
    router.include_router(pkg_edit_router)
    router.include_router(room_router)
    router.include_router(spec_router)
    router.include_router(reply_router)  # Catch-all последний


    return router
