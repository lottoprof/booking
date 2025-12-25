"""
bot/app/handlers/admin_reply.py

РОУТИНГ — связывает текст кнопки с действием.

Не знает о структуре клавиатур.
Не знает как отправлять сообщения.
Только: получил текст → вызвал нужный метод flow.
"""

from aiogram import Router
from aiogram.types import Message

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.flows.admin.menu import AdminMenuFlow

router = Router()


def setup(menu_controller, get_user_role):
    """
    Настройка роутера.
    
    Args:
        menu_controller: MenuController для передачи в flow
        get_user_role: функция получения роли пользователя
    """
    
    flow = AdminMenuFlow(menu_controller)

    @router.message()
    async def handle_admin_reply(message: Message):
        tg_id = message.from_user.id
        
        # Проверка роли
        if get_user_role(tg_id) != "admin":
            return

        lang = user_lang.get(tg_id, DEFAULT_LANG)
        text = message.text

        # ----------------------------------------------------------
        # MAIN MENU → Submenus
        # ----------------------------------------------------------
        
        if text == t("admin:main:settings", lang):
            await flow.to_settings(message, lang)

        elif text == t("admin:main:schedule", lang):
            await flow.to_schedule(message, lang)

        elif text == t("admin:main:clients", lang):
            await flow.to_clients(message, lang)

        # ----------------------------------------------------------
        # BACK → Main menu
        # ----------------------------------------------------------

        elif text in (
            t("admin:settings:back", lang),
            t("admin:schedule:back", lang),
            t("admin:clients:back", lang),
        ):
            await flow.back_to_main(message, lang)

        # ----------------------------------------------------------
        # Settings submenu items (TODO: implement flows)
        # ----------------------------------------------------------

        elif text == t("admin:settings:locations", lang):
            pass  # TODO: await flow.to_locations(message, lang)

        elif text == t("admin:settings:rooms", lang):
            pass  # TODO: await flow.to_rooms(message, lang)

        elif text == t("admin:settings:services", lang):
            pass  # TODO: await flow.to_services(message, lang)

        elif text == t("admin:settings:packages", lang):
            pass  # TODO: await flow.to_packages(message, lang)

        elif text == t("admin:settings:specialists", lang):
            pass  # TODO: await flow.to_specialists(message, lang)

        elif text == t("admin:settings:spec_services", lang):
            pass  # TODO: await flow.to_spec_services(message, lang)

        # ----------------------------------------------------------
        # Schedule submenu items
        # ----------------------------------------------------------

        elif text == t("admin:schedule:overrides", lang):
            pass  # TODO: await flow.to_overrides(message, lang)

        # ----------------------------------------------------------
        # Clients submenu items
        # ----------------------------------------------------------

        elif text == t("admin:clients:find", lang):
            pass  # TODO: await flow.to_find_client(message, lang)

        elif text == t("admin:clients:bookings", lang):
            pass  # TODO: await flow.to_client_bookings(message, lang)

        elif text == t("admin:clients:wallets", lang):
            pass  # TODO: await flow.to_wallets(message, lang)

    return router
