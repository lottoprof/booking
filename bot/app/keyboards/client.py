# bot/app/keyboards/client.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.app.i18n.loader import t


def client_main(lang: str) -> ReplyKeyboardMarkup:
    """
    Навигация клиента
    Главное Reply-меню клиента.
    Используется как якорь навигации.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("client:main:book", lang)),
            ],
            [
                KeyboardButton(text=t("client:main:bookings", lang)),
                KeyboardButton(text=t("client:main:services", lang)),
            ],
            [
                KeyboardButton(text=t("client:main:contact", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

