"""
bot/app/keyboards/specialist.py

Keyboards for specialist interface.
"""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from bot.app.i18n.loader import t


# ============================================================
# REPLY KEYBOARDS (navigation)
# ============================================================

def specialist_main(lang: str) -> ReplyKeyboardMarkup:
    """Main menu for specialists."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("specialist:main:schedule", lang)),
                KeyboardButton(text=t("specialist:main:gcal", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def specialist_gcal(lang: str) -> ReplyKeyboardMarkup:
    """Google Calendar submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("specialist:gcal:status", lang)),
            ],
            [
                KeyboardButton(text=t("specialist:gcal:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ============================================================
# INLINE KEYBOARDS (Google Calendar)
# ============================================================

def gcal_status_inline(lang: str, is_connected: bool, sync_enabled: bool) -> InlineKeyboardMarkup:
    """Inline keyboard for Google Calendar status view."""
    buttons = []

    if is_connected:
        # Toggle sync
        if sync_enabled:
            buttons.append([
                InlineKeyboardButton(
                    text=t("specialist:gcal:disable_sync", lang),
                    callback_data="gcal:toggle_sync:0"
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text=t("specialist:gcal:enable_sync", lang),
                    callback_data="gcal:toggle_sync:1"
                )
            ])
        # Disconnect
        buttons.append([
            InlineKeyboardButton(
                text=t("specialist:gcal:disconnect", lang),
                callback_data="gcal:disconnect"
            )
        ])
    else:
        # Connect
        buttons.append([
            InlineKeyboardButton(
                text=t("specialist:gcal:connect", lang),
                callback_data="gcal:connect"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def gcal_confirm_disconnect(lang: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard for disconnect."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common:yes", lang),
                    callback_data="gcal:disconnect:confirm"
                ),
                InlineKeyboardButton(
                    text=t("common:no", lang),
                    callback_data="gcal:disconnect:cancel"
                ),
            ],
        ]
    )
