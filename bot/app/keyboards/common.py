from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from bot.app.i18n.loader import get_available_langs, t


def language_inline():
    langs = get_available_langs()

    # если языков меньше двух — выбор не нужен
    if len(langs) < 2:
        return None

    buttons = []

    for lang in langs:
        key = f"common:lang:{lang}"

        # Используем ЭТОТ ЖЕ язык для получения названия
        # ru:common:lang:ru → "Русский"
        # en:common:lang:en → "English"
        label = t(key, lang=lang)
        
        if label == key:
            continue

        buttons.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"lang:{lang}"
            )
        )

    if not buttons:
        return None

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def request_phone_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """
    Клавиатура с кнопкой запроса контакта.
    
    request_contact=True — стандартная кнопка Telegram,
    показывает системный диалог подтверждения.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=t("registration:share_phone", lang),
                    request_contact=True
                )
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
