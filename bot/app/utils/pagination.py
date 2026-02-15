"""
bot/app/utils/pagination.py

Standard nav-row builder per tg_kbrd.md §15.
"""

from aiogram.types import InlineKeyboardButton

from bot.app.i18n.loader import t


def build_nav_row(
    page: int,
    total_pages: int,
    page_cb: str,
    noop_cb: str,
    lang: str,
) -> list[InlineKeyboardButton]:
    """
    Build a standard 3-button nav row: [prev | page/total | next].

    Returns empty list when total_pages <= 1 (no pagination needed).

    Args:
        page: current 0-based page index
        total_pages: total number of pages
        page_cb: callback template with ``{p}`` placeholder, e.g. ``"loc:page:{p}"``
        noop_cb: callback for disabled buttons, e.g. ``"loc:noop"``
        lang: user language code
    """
    if total_pages <= 1:
        return []

    row: list[InlineKeyboardButton] = []

    # prev
    if page > 0:
        row.append(InlineKeyboardButton(
            text=t("common:prev", lang),
            callback_data=page_cb.format(p=page - 1),
        ))
    else:
        row.append(InlineKeyboardButton(text=" ", callback_data=noop_cb))

    # counter
    row.append(InlineKeyboardButton(
        text=f"{page + 1}/{total_pages}",
        callback_data=noop_cb,
    ))

    # next
    if page < total_pages - 1:
        row.append(InlineKeyboardButton(
            text=t("common:next", lang),
            callback_data=page_cb.format(p=page + 1),
        ))
    else:
        row.append(InlineKeyboardButton(text=" ", callback_data=noop_cb))

    return row
