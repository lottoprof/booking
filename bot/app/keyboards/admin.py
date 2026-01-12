"""
bot/app/keyboards/admin.py

Клавиатуры админа.
- Reply: навигация (is_persistent=True)
- Inline keyboards перенесены в соответствующие flow-модули
"""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from bot.app.i18n.loader import t


# ============================================================
# REPLY KEYBOARDS (навигация)
# ============================================================

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
        is_persistent=True,
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


def admin_locations(lang: str) -> ReplyKeyboardMarkup:
    """Меню локаций."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:locations:list", lang)),
                KeyboardButton(text=t("admin:locations:create", lang)),
            ],
            [
                KeyboardButton(text=t("admin:locations:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_rooms(lang: str) -> ReplyKeyboardMarkup:
    """Меню комнат."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:rooms:list", lang)),
                KeyboardButton(text=t("admin:rooms:create", lang)),
            ],
            [
                KeyboardButton(text=t("admin:rooms:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_services(lang: str) -> ReplyKeyboardMarkup:
    """Меню услуг."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:services:list", lang)),
                KeyboardButton(text=t("admin:services:create", lang)),
            ],
            [
                KeyboardButton(text=t("admin:services:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_specialists(lang: str) -> ReplyKeyboardMarkup:
    """Меню специалистов."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:specialists:list", lang)),
                KeyboardButton(text=t("admin:specialists:create", lang)),
            ],
            [
                KeyboardButton(text=t("admin:specialists:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_packages(lang: str) -> ReplyKeyboardMarkup:
    """Меню пакетов услуг."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:packages:list", lang)),
                KeyboardButton(text=t("admin:packages:create", lang)),
            ],
            [
                KeyboardButton(text=t("admin:packages:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

