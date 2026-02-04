"""
bot/app/flows/specialist/google_calendar.py

Google Calendar integration flow for specialists.

Handles:
- Viewing integration status
- Connecting Google Calendar
- Enabling/disabling sync
- Disconnecting
"""

import logging
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.api import api
from bot.app.utils.state import user_lang
from bot.app.keyboards.specialist import (
    specialist_main,
    specialist_gcal,
    gcal_status_inline,
    gcal_confirm_disconnect,
)

logger = logging.getLogger(__name__)


class GoogleCalendarFlow:
    """Google Calendar integration flow for specialists."""

    def __init__(self, menu_controller, get_user_role):
        self.mc = menu_controller
        self.get_user_role = get_user_role
        self.router = Router(name="specialist_gcal")
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup callback handlers."""

        @self.router.callback_query(lambda c: c.data and c.data.startswith("gcal:"))
        async def handle_gcal_callback(callback: CallbackQuery, state: FSMContext):
            tg_id = callback.from_user.id
            role = self.get_user_role(tg_id)

            if role != "specialist":
                await callback.answer(t("common:error", DEFAULT_LANG), show_alert=True)
                return

            lang = user_lang.get(tg_id, DEFAULT_LANG)
            data = callback.data

            if data == "gcal:connect":
                await self._handle_connect(callback, lang)
            elif data == "gcal:disconnect":
                await self._handle_disconnect_prompt(callback, lang)
            elif data == "gcal:disconnect:confirm":
                await self._handle_disconnect_confirm(callback, lang)
            elif data == "gcal:disconnect:cancel":
                await self._handle_disconnect_cancel(callback, lang)
            elif data.startswith("gcal:toggle_sync:"):
                enable = data.split(":")[-1] == "1"
                await self._handle_toggle_sync(callback, lang, enable)

    async def _get_specialist_id(self, tg_id: int) -> int | None:
        """Get specialist ID from user's tg_id."""
        users = await api.get_users()
        user = next((u for u in users if u.get("tg_id") == tg_id), None)
        if not user:
            return None

        specialist = await api.get_specialist_by_user_id(user["id"])
        if not specialist:
            return None

        return specialist["id"]

    async def show_status(self, message: Message) -> None:
        """Show Google Calendar integration status."""
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)

        specialist_id = await self._get_specialist_id(tg_id)
        if not specialist_id:
            await message.answer(t("specialist:gcal:not_specialist", lang))
            return

        status = await api.get_integration_status(specialist_id)

        if not status:
            # Not connected
            text = f"{t('specialist:gcal:title', lang)}\n\n"
            text += f"{t('specialist:gcal:status_off', lang)}"
            kb = gcal_status_inline(lang, is_connected=False, sync_enabled=False)
        else:
            is_connected = status.get("is_connected", False)
            sync_enabled = status.get("sync_enabled", False)

            text = f"{t('specialist:gcal:title', lang)}\n\n"
            if is_connected:
                text += f"{t('specialist:gcal:status_on', lang)}\n"
                if sync_enabled:
                    text += f"{t('specialist:gcal:sync_on', lang)}"
                else:
                    text += f"{t('specialist:gcal:sync_off', lang)}"

                if status.get("last_sync_at"):
                    text += f"\n\n{t('specialist:gcal:last_sync', lang)}: {status['last_sync_at']}"
            else:
                text += f"{t('specialist:gcal:status_off', lang)}"

            kb = gcal_status_inline(lang, is_connected, sync_enabled)

        await self.mc.show_inline_readonly(message, text, kb)

    async def _handle_connect(self, callback: CallbackQuery, lang: str) -> None:
        """Handle connect button click."""
        tg_id = callback.from_user.id

        specialist_id = await self._get_specialist_id(tg_id)
        if not specialist_id:
            await callback.answer(t("specialist:gcal:not_specialist", lang), show_alert=True)
            return

        auth_url = await api.get_google_auth_url(specialist_id)
        if not auth_url:
            await callback.answer(t("specialist:gcal:connect_error", lang), show_alert=True)
            return

        # Send auth link
        text = f"{t('specialist:gcal:auth_link', lang)}\n\n{auth_url}"
        await callback.message.answer(text)
        await callback.answer()

    async def _handle_disconnect_prompt(self, callback: CallbackQuery, lang: str) -> None:
        """Show disconnect confirmation."""
        text = t("specialist:gcal:disconnect_confirm", lang)
        kb = gcal_confirm_disconnect(lang)
        await self.mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    async def _handle_disconnect_confirm(self, callback: CallbackQuery, lang: str) -> None:
        """Handle disconnect confirmation."""
        tg_id = callback.from_user.id

        specialist_id = await self._get_specialist_id(tg_id)
        if not specialist_id:
            await callback.answer(t("specialist:gcal:not_specialist", lang), show_alert=True)
            return

        success = await api.disconnect_google_calendar(specialist_id)
        if success:
            await callback.answer(t("specialist:gcal:disconnected", lang), show_alert=True)
            # Refresh status view
            text = f"{t('specialist:gcal:title', lang)}\n\n"
            text += f"{t('specialist:gcal:status_off', lang)}"
            kb = gcal_status_inline(lang, is_connected=False, sync_enabled=False)
            await self.mc.edit_inline(callback.message, text, kb)
        else:
            await callback.answer(t("specialist:gcal:disconnect_error", lang), show_alert=True)

    async def _handle_disconnect_cancel(self, callback: CallbackQuery, lang: str) -> None:
        """Handle disconnect cancellation."""
        tg_id = callback.from_user.id

        specialist_id = await self._get_specialist_id(tg_id)
        if not specialist_id:
            await callback.answer()
            return

        status = await api.get_integration_status(specialist_id)
        is_connected = status.get("is_connected", False) if status else False
        sync_enabled = status.get("sync_enabled", False) if status else False

        text = f"{t('specialist:gcal:title', lang)}\n\n"
        if is_connected:
            text += f"{t('specialist:gcal:status_on', lang)}\n"
            if sync_enabled:
                text += f"{t('specialist:gcal:sync_on', lang)}"
            else:
                text += f"{t('specialist:gcal:sync_off', lang)}"
        else:
            text += f"{t('specialist:gcal:status_off', lang)}"

        kb = gcal_status_inline(lang, is_connected, sync_enabled)
        await self.mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    async def _handle_toggle_sync(self, callback: CallbackQuery, lang: str, enable: bool) -> None:
        """Handle sync toggle."""
        tg_id = callback.from_user.id

        specialist_id = await self._get_specialist_id(tg_id)
        if not specialist_id:
            await callback.answer(t("specialist:gcal:not_specialist", lang), show_alert=True)
            return

        result = await api.update_integration(specialist_id, sync_enabled=enable)
        if not result:
            await callback.answer(t("specialist:gcal:update_error", lang), show_alert=True)
            return

        if enable:
            await callback.answer(t("specialist:gcal:sync_enabled", lang), show_alert=True)
        else:
            await callback.answer(t("specialist:gcal:sync_disabled", lang), show_alert=True)

        # Refresh view
        text = f"{t('specialist:gcal:title', lang)}\n\n"
        text += f"{t('specialist:gcal:status_on', lang)}\n"
        if enable:
            text += f"{t('specialist:gcal:sync_on', lang)}"
        else:
            text += f"{t('specialist:gcal:sync_off', lang)}"

        kb = gcal_status_inline(lang, is_connected=True, sync_enabled=enable)
        await self.mc.edit_inline(callback.message, text, kb)


def setup(menu_controller, get_user_role) -> Router:
    """Setup Google Calendar flow and return router."""
    flow = GoogleCalendarFlow(menu_controller, get_user_role)
    flow.router.show_status = flow.show_status
    return flow.router
