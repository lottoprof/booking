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

    labels = []
    for lang in langs:
        label = t("common:lang:choose", lang=lang)
        if label != "common:lang:choose":
            labels.append((lang, label))

    if not labels:
        return None

    # Находим максимальную длину
    max_len = max(len(label) for _, label in labels)
    
    # Ширина кнопки (минимум 30 символов для растягивания)
    button_width = max(max_len + 16, 30)

    buttons = []
    for lang, label in labels:
        # Центрируем текст
        padded_label = label.center(button_width)
        
        buttons.append([
            InlineKeyboardButton(
                text=padded_label,
                callback_data=f"lang:{lang}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
