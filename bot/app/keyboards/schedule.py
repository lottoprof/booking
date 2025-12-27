"""
bot/app/keyboards/schedule.py

Inline-клавиатуры для редактирования графика.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.app.i18n.loader import t
from bot.app.utils.schedule_helper import DAYS, format_day_value


def schedule_days_inline(
    schedule: dict,
    lang: str,
    prefix: str = "sched"
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора дня недели.
    
    [Пн 09:00-18:00] [Вт 09:00-18:00]
    [Ср 09:00-18:00] [Чт 09:00-18:00]
    [Пт 09:00-18:00] [Сб вых]
    [Вс вых]
    ─────────────────
    [💾 Сохранить] [❌ Отмена]
    
    callback_data: {prefix}:day:{day}
    """
    buttons = []
    row = []
    
    for day in DAYS:
        day_name = t(f"day:{day}", lang)
        day_value = format_day_value(schedule.get(day), lang)
        
        btn = InlineKeyboardButton(
            text=f"{day_name} {day_value}",
            callback_data=f"{prefix}:day:{day}"
        )
        row.append(btn)
        
        # По 2 кнопки в ряд
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    # Остаток (воскресенье)
    if row:
        buttons.append(row)
    
    # Сохранить / Отмена
    buttons.append([
        InlineKeyboardButton(
            text=t("schedule:save", lang),
            callback_data=f"{prefix}:save"
        ),
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"{prefix}:cancel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def schedule_day_edit_inline(
    day: str,
    schedule: dict,
    lang: str,
    prefix: str = "sched"
) -> InlineKeyboardMarkup:
    """
    Клавиатура редактирования одного дня.
    
    [😴 Выходной]
    [⬅️ Назад]
    
    callback_data: {prefix}:dayoff:{day}
    """
    buttons = [
        [InlineKeyboardButton(
            text=t("schedule:day_off", lang),
            callback_data=f"{prefix}:dayoff:{day}"
        )],
        [InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data=f"{prefix}:back"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
