"""
bot/app/keyboards/admin.py

Клавиатуры админа.
- Reply: навигация (is_persistent=True)
- Inline: работа с данными
"""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from bot.app.i18n.loader import t
import math

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


# ============================================================
# INLINE KEYBOARDS (работа с данными)
# ============================================================

def locations_list_inline(
    locations: list[dict],
    page: int = 0,
    per_page: int = 5,
    lang: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Список локаций с пагинацией.
    
    callback_data:
    - loc:view:{id} — просмотр
    - loc:page:{n}  — страница
    - loc:search    — поиск
    - loc:back      — назад в Reply
    """
    buttons = []
    
    # Фиксированные кнопки сверху
    buttons.append([
        InlineKeyboardButton(
            text=t("admin:locations:search", lang),
            callback_data="loc:search"
        ),
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="loc:back"
        ),
    ])
    
    # Пагинация расчёт
    total = len(locations)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    start = page * per_page
    end = start + per_page
    page_items = locations[start:end]
    
    # Список локаций
    for loc in page_items:
        buttons.append([
            InlineKeyboardButton(
                text=t("admin:locations:item", lang, loc["name"]),
                callback_data=f"loc:view:{loc['id']}"
            )
        ])
    
    # Кнопки пагинации
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text=t("common:prev", lang),
                    callback_data=f"loc:page:{page - 1}"
                )
            )
        if page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton(
                    text=t("common:next", lang),
                    callback_data=f"loc:page:{page + 1}"
                )
            )
        if nav_row:
            buttons.append(nav_row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def location_view_inline(location_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Просмотр локации."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:location:edit", lang),
                callback_data=f"loc:edit:{location_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:location:delete", lang),
                callback_data=f"loc:del:{location_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("admin:location:back", lang),
                callback_data="loc:list"
            ),
        ],
    ])


def location_delete_confirm_inline(location_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:yes", lang),
                callback_data=f"loc:del_yes:{location_id}"
            ),
            InlineKeyboardButton(
                text=t("common:no", lang),
                callback_data="loc:list"
            ),
        ],
    ])


def location_create_inline(lang: str = "ru") -> InlineKeyboardMarkup:
    """Форма создания — кнопка отмены."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:cancel", lang),
                callback_data="loc:back"
            ),
        ],
    ])

# ============================================================
# SERVICES - Reply keyboard
# ============================================================

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


# ============================================================
# SERVICES - Inline keyboards
# ============================================================

def _format_service_item(svc: dict, lang: str) -> str:
    """
    Форматирует услугу для отображения в списке.
    
    Формат: 🛎  Название | 60+10 мин | 2500₽
    или:    🛎  Название | 60 мин | 2500₽ (без перерыва)
    """
    name = svc.get("name", "?")
    duration = svc.get("duration_min", 0)
    break_min = svc.get("break_min", 0)
    price = svc.get("price", 0)

    # Время: "60+10" или просто "60"
    if break_min > 0:
        time_str = f"{duration}+{break_min}"
    else:
        time_str = str(duration)

    # Цена: целое число если без копеек
    if price == int(price):
        price_str = f"{int(price)}{t('common:currency', lang)}"
    else:
        price_str = f"{price:.0f}{t('common:currency', lang)}"

    return f"{t('admin:services:item_icon', lang)} {name} | {time_str}{t('common:min', lang)} | {price_str}"


def services_list_inline(
    services: list[dict],
    page: int,
    lang: str,
    per_page: int = 5
) -> InlineKeyboardMarkup:
    """Список услуг с пагинацией."""
    total = len(services)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_items = services[start:end]

    buttons = []

    # Кнопки услуг
    for svc in page_items:
        buttons.append([
            InlineKeyboardButton(
                text=_format_service_item(svc, lang),
                callback_data=f"svc:view:{svc['id']}"
            )
        ])

    # Пагинация
    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text=t("common:prev", lang),
                callback_data=f"svc:page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="svc:noop"
            ))

        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="svc:noop"
        ))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text=t("common:next", lang),
                callback_data=f"svc:page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="svc:noop"
            ))

        buttons.append(nav_row)

    # Назад
    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="svc:back"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def service_view_inline(service: dict, lang: str) -> InlineKeyboardMarkup:
    """Карточка просмотра услуги."""
    svc_id = service["id"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:service:edit", lang),
                callback_data=f"svc:edit:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:service:delete", lang),
                callback_data=f"svc:delete:{svc_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data="svc:list:0"
            )
        ]
    ])


def service_delete_confirm_inline(svc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:yes", lang),
                callback_data=f"svc:delete_confirm:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("common:no", lang),
                callback_data=f"svc:view:{svc_id}"
            )
        ]
    ])


def service_cancel_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при создании."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="svc_create:cancel"
        )
    ]])


def service_skip_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка пропустить + отмена."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:skip", lang),
                callback_data="svc_create:skip"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:cancel", lang),
                callback_data="svc_create:cancel"
            )
        ]
    ])


# ============================================================
# COLOR PICKER
# ============================================================

def get_color_codes(lang: str) -> list[str]:
    """Получить список кодов цветов из i18n."""
    colors_str = t("colors:list", lang)
    return [c.strip() for c in colors_str.split(",") if c.strip()]


def color_picker_inline(lang: str) -> InlineKeyboardMarkup:
    """Выбор цвета услуги (создание)."""
    buttons = []
    row = []

    for color_code in get_color_codes(lang):
        emoji = t(f"color:{color_code}", lang)
        row.append(InlineKeyboardButton(
            text=emoji,
            callback_data=f"svc_color:{color_code}"
        ))

        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Без цвета
    buttons.append([
        InlineKeyboardButton(
            text=t("admin:service:color_none", lang),
            callback_data="svc_color:none"
        )
    ])

    # Отмена
    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="svc_create:cancel"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

