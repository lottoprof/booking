# bot/app/keyboards/client.py

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from bot.app.i18n.loader import t


def client_main(lang: str) -> ReplyKeyboardMarkup:
    """
    Навигация клиента
    Главное Reply-меню клиента.
    Используется как якорь навигации.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            # [KeyboardButton(text=t("client:main:book", lang))],  # disabled — miniapp only
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


def contact_support_inline(support_tg_id: int, lang: str) -> InlineKeyboardMarkup:
    """
    Inline-кнопка для открытия чата с сотрудником.
    Использует tg://user?id=... deeplink.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("client:main:contact", lang),  # "Связаться с нами"
                url=f"tg://user?id={support_tg_id}"
            ),
        ],
    ])

