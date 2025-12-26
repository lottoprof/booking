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
                KeyboardButton(text=t("admin:settings:spec_services", lang)),
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
