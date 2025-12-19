from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.i18n.loader import get_available_langs, t


def language_inline():
    langs = get_available_langs()

    # если языков меньше двух — выбор не нужен
    if len(langs) < 2:
        return None

    buttons = []

    for lang in langs:
        key = f"common:lang:{lang}"

        # если нет подписи языка — кнопку не показываем
        label = t(key, lang=None)
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

