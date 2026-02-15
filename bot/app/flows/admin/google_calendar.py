"""
bot/app/flows/admin/google_calendar.py

Google Calendar integration flow for admins.

Syncs all bookings across all locations to admin's Google Calendar.
"""

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.keyboards.admin import admin_settings  # noqa: F401
from bot.app.utils.api import api
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)


def gcal_admin_status_inline(lang: str, is_connected: bool, sync_enabled: bool) -> InlineKeyboardMarkup:
    """Inline keyboard for admin Google Calendar status."""
    buttons = []

    if is_connected:
        if sync_enabled:
            buttons.append([
                InlineKeyboardButton(
                    text=t("admin:gcal:disable_sync", lang),
                    callback_data="admin_gcal:toggle_sync:0"
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text=t("admin:gcal:enable_sync", lang),
                    callback_data="admin_gcal:toggle_sync:1"
                )
            ])
        buttons.append([
            InlineKeyboardButton(
                text=t("admin:gcal:disconnect", lang),
                callback_data="admin_gcal:disconnect"
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text=t("admin:gcal:connect", lang),
                callback_data="admin_gcal:connect"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def gcal_admin_confirm_disconnect(lang: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard for disconnect."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common:yes", lang),
                    callback_data="admin_gcal:disconnect:confirm"
                ),
                InlineKeyboardButton(
                    text=t("common:no", lang),
                    callback_data="admin_gcal:disconnect:cancel"
                ),
            ],
        ]
    )


class AdminGoogleCalendarFlow:
    """Google Calendar integration flow for admins."""

    def __init__(self, menu_controller, get_user_role):
        self.mc = menu_controller
        self.get_user_role = get_user_role
        self.router = Router(name="admin_gcal")
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup callback handlers."""

        @self.router.callback_query(lambda c: c.data and c.data.startswith("admin_gcal:"))
        async def handle_admin_gcal_callback(callback: CallbackQuery, state: FSMContext):
            tg_id = callback.from_user.id
            role = self.get_user_role(tg_id)

            if role != "admin":
                await callback.answer(t("common:error", DEFAULT_LANG), show_alert=True)
                return

            lang = user_lang.get(tg_id, DEFAULT_LANG)
            data = callback.data

            if data == "admin_gcal:connect":
                await self._handle_connect(callback, lang)
            elif data == "admin_gcal:disconnect":
                await self._handle_disconnect_prompt(callback, lang)
            elif data == "admin_gcal:disconnect:confirm":
                await self._handle_disconnect_confirm(callback, lang)
            elif data == "admin_gcal:disconnect:cancel":
                await self._handle_disconnect_cancel(callback, lang)
            elif data.startswith("admin_gcal:toggle_sync:"):
                enable = data.split(":")[-1] == "1"
                await self._handle_toggle_sync(callback, lang, enable)

    async def _get_user_id(self, tg_id: int) -> int | None:
        """Get user ID from tg_id."""
        users = await api.get_users()
        user = next((u for u in users if u.get("tg_id") == tg_id), None)
        if user:
            return user["id"]
        return None

    async def show_status(self, message: Message) -> None:
        """Show Google Calendar integration status for admin."""
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)

        user_id = await self._get_user_id(tg_id)
        if not user_id:
            await message.answer(t("admin:gcal:not_found", lang))
            return

        status = await api.get_user_integration_status(user_id)

        if not status or not status.get("is_connected"):
            text = f"{t('admin:gcal:title', lang)}\n\n"
            text += f"{t('admin:gcal:status_off', lang)}\n\n"
            text += f"{t('admin:gcal:description', lang)}"
            kb = gcal_admin_status_inline(lang, is_connected=False, sync_enabled=False)
        else:
            is_connected = status.get("is_connected", False)
            sync_enabled = status.get("sync_enabled", False)

            text = f"{t('admin:gcal:title', lang)}\n\n"
            text += f"{t('admin:gcal:status_on', lang)}\n"
            if sync_enabled:
                text += f"{t('admin:gcal:sync_on', lang)}"
            else:
                text += f"{t('admin:gcal:sync_off', lang)}"

            if status.get("last_sync_at"):
                text += f"\n\n{t('admin:gcal:last_sync', lang)}: {status['last_sync_at']}"

            kb = gcal_admin_status_inline(lang, is_connected, sync_enabled)

        await self.mc.show_inline_readonly(message, text, kb)

    async def _handle_connect(self, callback: CallbackQuery, lang: str) -> None:
        """Handle connect button click."""
        tg_id = callback.from_user.id

        user_id = await self._get_user_id(tg_id)
        if not user_id:
            await callback.answer(t("admin:gcal:not_found", lang), show_alert=True)
            return

        # Get auth URL for admin with sync_scope='all'
        auth_url = await api.get_google_auth_url(user_id=user_id, sync_scope="all")
        if not auth_url:
            await callback.answer(t("admin:gcal:connect_error", lang), show_alert=True)
            return

        text = f"{t('admin:gcal:auth_link', lang)}\n\n{auth_url}"
        await callback.message.answer(text)
        await callback.answer()

    async def _handle_disconnect_prompt(self, callback: CallbackQuery, lang: str) -> None:
        """Show disconnect confirmation."""
        text = t("admin:gcal:disconnect_confirm", lang)
        kb = gcal_admin_confirm_disconnect(lang)
        await self.mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    async def _handle_disconnect_confirm(self, callback: CallbackQuery, lang: str) -> None:
        """Handle disconnect confirmation."""
        tg_id = callback.from_user.id

        user_id = await self._get_user_id(tg_id)
        if not user_id:
            await callback.answer(t("admin:gcal:not_found", lang), show_alert=True)
            return

        success = await api.disconnect_user_google_calendar(user_id)
        if success:
            await callback.answer(t("admin:gcal:disconnected", lang), show_alert=True)
            text = f"{t('admin:gcal:title', lang)}\n\n"
            text += f"{t('admin:gcal:status_off', lang)}\n\n"
            text += f"{t('admin:gcal:description', lang)}"
            kb = gcal_admin_status_inline(lang, is_connected=False, sync_enabled=False)
            await self.mc.edit_inline(callback.message, text, kb)
        else:
            await callback.answer(t("admin:gcal:disconnect_error", lang), show_alert=True)

    async def _handle_disconnect_cancel(self, callback: CallbackQuery, lang: str) -> None:
        """Handle disconnect cancellation."""
        tg_id = callback.from_user.id

        user_id = await self._get_user_id(tg_id)
        if not user_id:
            await callback.answer()
            return

        status = await api.get_user_integration_status(user_id)
        is_connected = status.get("is_connected", False) if status else False
        sync_enabled = status.get("sync_enabled", False) if status else False

        text = f"{t('admin:gcal:title', lang)}\n\n"
        if is_connected:
            text += f"{t('admin:gcal:status_on', lang)}\n"
            if sync_enabled:
                text += f"{t('admin:gcal:sync_on', lang)}"
            else:
                text += f"{t('admin:gcal:sync_off', lang)}"
        else:
            text += f"{t('admin:gcal:status_off', lang)}\n\n"
            text += f"{t('admin:gcal:description', lang)}"

        kb = gcal_admin_status_inline(lang, is_connected, sync_enabled)
        await self.mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    async def _handle_toggle_sync(self, callback: CallbackQuery, lang: str, enable: bool) -> None:
        """Handle sync toggle."""
        tg_id = callback.from_user.id

        user_id = await self._get_user_id(tg_id)
        if not user_id:
            await callback.answer(t("admin:gcal:not_found", lang), show_alert=True)
            return

        result = await api.update_user_integration(user_id, sync_enabled=enable)
        if not result:
            await callback.answer(t("admin:gcal:update_error", lang), show_alert=True)
            return

        if enable:
            await callback.answer(t("admin:gcal:sync_enabled", lang), show_alert=True)
        else:
            await callback.answer(t("admin:gcal:sync_disabled", lang), show_alert=True)

        text = f"{t('admin:gcal:title', lang)}\n\n"
        text += f"{t('admin:gcal:status_on', lang)}\n"
        if enable:
            text += f"{t('admin:gcal:sync_on', lang)}"
        else:
            text += f"{t('admin:gcal:sync_off', lang)}"

        kb = gcal_admin_status_inline(lang, is_connected=True, sync_enabled=enable)
        await self.mc.edit_inline(callback.message, text, kb)


def setup(menu_controller, get_user_role) -> Router:
    """Setup admin Google Calendar flow and return router."""
    flow = AdminGoogleCalendarFlow(menu_controller, get_user_role)
    flow.router.show_status = flow.show_status
    return flow.router
