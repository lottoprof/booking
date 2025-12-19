from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from app.i18n.loader import t


def admin_main(lang: str):
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
        resize_keyboard=True
    )


def admin_settings(lang: str):
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
        resize_keyboard=True
    )


def admin_schedule(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:schedule:overrides", lang)),
            ],
            [
                KeyboardButton(text=t("admin:schedule:back", lang)),
            ],
        ],
        resize_keyboard=True
    )


def admin_clients(lang: str):
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
        resize_keyboard=True
    )

