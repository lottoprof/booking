"""
bot/app/keyboards/admin.py

Клавиатуры админа с is_persistent=True для стабильности на Android.
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.app.i18n.loader import t


def admin_main(lang: str) -> ReplyKeyboardMarkup:
    """Главное меню админа."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:main:settings", lang)),
                KeyboardButton(text=t("admin:main:schedule", lang)),
            ],
            [
                KeyboardButton(text=t("admin:main:clients", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,  # Держит клавиатуру на Android
    )


def admin_settings(lang: str) -> ReplyKeyboardMarkup:
    """Подменю настроек."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:settings:locations", lang)),
                KeyboardButton(text=t("admin:settings:rooms", lang)),
            ],
            [
                KeyboardButton(text=t("admin:settings:services", lang)),
                KeyboardButton(text=t("admin:settings:packages", lang)),
            ],
            [
                KeyboardButton(text=t("admin:settings:specialists", lang)),
                KeyboardButton(text=t("admin:settings:spec_services", lang)),
            ],
            [
                KeyboardButton(text=t("admin:settings:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_schedule(lang: str) -> ReplyKeyboardMarkup:
    """Подменю расписания."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:schedule:overrides", lang)),
            ],
            [
                KeyboardButton(text=t("admin:schedule:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_clients(lang: str) -> ReplyKeyboardMarkup:
    """Подменю клиентов."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:clients:find", lang)),
                KeyboardButton(text=t("admin:clients:bookings", lang)),
            ],
            [
                KeyboardButton(text=t("admin:clients:wallets", lang)),
            ],
            [
                KeyboardButton(text=t("admin:clients:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

