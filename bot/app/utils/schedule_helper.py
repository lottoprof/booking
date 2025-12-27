"""
bot/app/utils/schedule_helper.py

Работа с графиком работы (work_schedule).

Формат JSON:
{
  "mon": {"start": "09:00", "end": "18:00"},
  "tue": {"start": "09:30", "end": "19:30"},
  "sat": null,  // выходной
  ...
}
"""

import re
from typing import Optional
from bot.app.i18n.loader import t

# Дни недели (ключи)
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def day_name(day: str, lang: str) -> str:
    """Короткое название дня из i18n."""
    return t(f"day:{day}", lang)


def day_name_full(day: str, lang: str) -> str:
    """Полное название дня из i18n."""
    return t(f"day:{day}:full", lang)


def empty_schedule() -> dict:
    """Пустой график (все дни — выходные)."""
    return {day: None for day in DAYS}


def default_schedule() -> dict:
    """Стандартный график Пн-Пт 09:00-18:00."""
    schedule = {}
    for day in DAYS:
        if day in ("sat", "sun"):
            schedule[day] = None
        else:
            schedule[day] = {"start": "09:00", "end": "18:00"}
    return schedule


def parse_time_input(text: str) -> Optional[dict] | str:
    """
    Парсит ввод пользователя.
    
    Входы:
    - "09:30-19:30" → {"start": "09:30", "end": "19:30"}
    - "0"           → None (выходной)
    
    Returns:
    - dict {"start": ..., "end": ...}
    - None (выходной)
    - "error" если не распознано
    """
    text = text.strip()
    
    if text == "0":
        return None
    
    pattern = r'^(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})$'
    match = re.match(pattern, text)
    
    if not match:
        return "error"
    
    h1, m1, h2, m2 = match.groups()
    h1, h2 = int(h1), int(h2)
    m1, m2 = int(m1), int(m2)
    
    if not (0 <= h1 <= 23 and 0 <= h2 <= 23):
        return "error"
    if not (0 <= m1 <= 59 and 0 <= m2 <= 59):
        return "error"
    
    start = f"{h1:02d}:{m1:02d}"
    end = f"{h2:02d}:{m2:02d}"
    
    return {"start": start, "end": end}


def format_day_value(day_data: Optional[dict], lang: str = "ru") -> str:
    """
    Форматирует значение для одного дня.
    
    - {"start": "09:00", "end": "18:00"} → "09:00-18:00"
    - None → "вых" / "off"
    """
    if day_data is None:
        return t("schedule:off", lang)
    
    return f"{day_data['start']}-{day_data['end']}"


def format_schedule_full(schedule: dict, lang: str = "ru") -> str:
    """
    Полный график для отображения.
    
    Понедельник: 09:00-18:00
    ...
    """
    lines = []
    for day in DAYS:
        name = day_name_full(day, lang)
        value = format_day_value(schedule.get(day), lang)
        lines.append(f"{name}: {value}")
    
    return "\n".join(lines)


def format_schedule_compact(schedule: dict, lang: str = "ru") -> str:
    """
    Компактный график: "Пн-Пт 09:00-18:00, Сб-Вс вых"
    """
    off = t("schedule:off", lang)
    
    groups = []
    current_group = {"days": [], "data": None}
    
    for day in DAYS:
        day_data = schedule.get(day)
        
        if day_data == current_group["data"]:
            current_group["days"].append(day)
        else:
            if current_group["days"]:
                groups.append(current_group)
            current_group = {"days": [day], "data": day_data}
    
    if current_group["days"]:
        groups.append(current_group)
    
    parts = []
    for group in groups:
        days = group["days"]
        data = group["data"]
        
        if len(days) == 1:
            day_str = day_name(days[0], lang)
        else:
            day_str = f"{day_name(days[0], lang)}-{day_name(days[-1], lang)}"
        
        if data is None:
            time_str = off
        else:
            time_str = f"{data['start']}-{data['end']}"
        
        parts.append(f"{day_str} {time_str}")
    
    return ", ".join(parts)
