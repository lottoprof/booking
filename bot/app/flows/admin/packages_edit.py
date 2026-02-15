"""
bot/app/flows/admin/packages_edit.py

EDIT-FSM for Service Packages (admin).

Правила:
- FSM в Redis (aiogram storage)
- PATCH только diff (changes)
- Inline-only
- Не управляет Reply/menu_context (это делает packages.py)

Особенности:
- Редактирование состава: multi-select услуг + inline qty single-select [1][5][10]
- show_on_pricing / show_on_booking toggles
- Описание: кнопка "Очистить"
- Edit menu показывает текущие значения + pending changes
"""

import json
import logging
import math
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.i18n.loader import DEFAULT_LANG, t, t_all
from bot.app.keyboards.admin import admin_packages
from bot.app.utils.api import api
from bot.app.utils.pagination import build_nav_row
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 8


# ==============================================================
# FSM States (EDIT)
# ==============================================================

class PackageEdit(StatesGroup):
    name = State()
    description = State()
    items = State()       # multi-select
    quantity = State()    # inline qty select for items


# ==============================================================
# Helpers
# ==============================================================

def build_package_edit_text(original: dict, changes: dict, lang: str) -> str:
    """Build edit screen text showing current values + pending changes."""
    name = changes.get("name", original.get("name") or "?")
    lines = [t("admin:package:edit_title", lang), ""]
    lines.append(f"📦 {name}")

    # description
    desc = changes.get("description", original.get("description"))
    if desc is not None:
        # changes may set description to None explicitly
        if "description" in changes and changes["description"] is None:
            pass  # cleared
        else:
            lines.append(f"📝 {desc}")

    # items
    items_raw = original.get("package_items") or []
    if isinstance(items_raw, str):
        try:
            items_raw = json.loads(items_raw)
        except Exception:
            items_raw = []
    if isinstance(items_raw, dict):
        items_raw = [items_raw]

    if "package_items" in changes:
        try:
            items_display = json.loads(changes["package_items"])
        except Exception:
            items_display = items_raw
    else:
        items_display = items_raw

    if isinstance(items_display, list) and items_display:
        qty = items_display[0].get("quantity", 1)
        lines.append(f"🛎 ×{qty}")

    # price
    price = original.get("package_price")
    if price is not None:
        lines.append(f"💰 {price}")

    # show_on flags
    sop = changes.get("show_on_pricing", original.get("show_on_pricing", True))
    sob = changes.get("show_on_booking", original.get("show_on_booking", True))
    p_icon = "✅" if sop else "❌"
    b_icon = "✅" if sob else "❌"
    lines.append(f"📊 pricing: {p_icon} | booking: {b_icon}")

    # pending changes indicator
    change_lines = []
    if "name" in changes:
        change_lines.append(f"✏️ name → \"{changes['name']}\"")
    if "description" in changes:
        if changes["description"] is None:
            change_lines.append("✏️ description → (cleared)")
        else:
            change_lines.append(f"✏️ description → \"{changes['description']}\"")
    if "package_items" in changes:
        change_lines.append("✏️ items → (changed)")
    if "show_on_pricing" in changes:
        change_lines.append(f"✏️ pricing → {'✅' if changes['show_on_pricing'] else '❌'}")
    if "show_on_booking" in changes:
        change_lines.append(f"✏️ booking → {'✅' if changes['show_on_booking'] else '❌'}")

    if change_lines:
        lines.append("")
        lines.extend(change_lines)

    return "\n".join(lines)


def pkg_edit_inline(pkg_id: int, original: dict, changes: dict, lang: str) -> InlineKeyboardMarkup:
    sop = changes.get("show_on_pricing", original.get("show_on_pricing", True))
    sob = changes.get("show_on_booking", original.get("show_on_booking", True))
    sop_icon = "✅" if sop else "❌"
    sob_icon = "✅" if sob else "❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:package:edit_name", lang), callback_data=f"pkg:edit_name:{pkg_id}"),
            InlineKeyboardButton(text=t("admin:package:edit_description", lang), callback_data=f"pkg:edit_desc:{pkg_id}"),
        ],
        [
            InlineKeyboardButton(text=t("admin:package:edit_services", lang), callback_data=f"pkg:edit_items:{pkg_id}"),
        ],
        [
            InlineKeyboardButton(text=f"📊 Pricing: {sop_icon}", callback_data=f"pkg:toggle_pricing:{pkg_id}"),
            InlineKeyboardButton(text=f"📋 Booking: {sob_icon}", callback_data=f"pkg:toggle_booking:{pkg_id}"),
        ],
        [
            InlineKeyboardButton(text=t("common:save", lang), callback_data=f"pkg:save:{pkg_id}"),
            InlineKeyboardButton(text=t("common:back", lang), callback_data=f"pkg:view:{pkg_id}"),
        ],
    ])


def pkg_edit_cancel_inline(pkg_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"pkg:edit:{pkg_id}")
    ]])


def pkg_edit_clear_cancel_inline(pkg_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("common:clear", lang), callback_data=f"pkg:clear_desc:{pkg_id}")],
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"pkg:edit:{pkg_id}")],
    ])


def pkg_items_multiselect_inline(
    services: list[dict],
    selected_ids: set[int],
    page: int,
    lang: str,
    pkg_id: int,
) -> InlineKeyboardMarkup:
    total = len(services)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, pages - 1))

    start = page * PAGE_SIZE
    chunk = services[start:start + PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for s in chunk:
        sid = int(s["id"])
        name = s.get("name") or "?"
        mark = "✅ " if sid in selected_ids else ""
        rows.append([
            InlineKeyboardButton(text=f"{mark}{name}", callback_data=f"pkg_edit:svc:{pkg_id}:{sid}")
        ])

    nav = build_nav_row(page, pages, f"pkg_edit:page:{pkg_id}:{{p}}", "pkg_edit:noop", lang)
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text=t("admin:package:services_selected", lang) % len(selected_ids), callback_data=f"pkg_edit:items_done:{pkg_id}"),
        InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"pkg:edit:{pkg_id}"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def pkg_edit_qty_inline(pkg_id: int, lang: str) -> InlineKeyboardMarkup:
    """Single-select qty [1][5][10] for EDIT items."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data=f"pkg_edit:qty:{pkg_id}:1"),
            InlineKeyboardButton(text="5", callback_data=f"pkg_edit:qty:{pkg_id}:5"),
            InlineKeyboardButton(text="10", callback_data=f"pkg_edit:qty:{pkg_id}:10"),
        ],
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"pkg:edit:{pkg_id}")],
    ])


# ==============================================================
# Public entry
# ==============================================================

async def start_package_edit(mc, callback: CallbackQuery, state: FSMContext, pkg_id: int):
    lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

    pkg = await api.get_package(pkg_id)
    await state.clear()
    await state.update_data(pkg_id=pkg_id, original=pkg, changes={})
    await state.set_state(None)

    text = build_package_edit_text(pkg, {}, lang)
    await mc.edit_inline(callback.message, text, pkg_edit_inline(pkg_id, pkg, {}, lang))


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    router = Router(name="packages_edit")
    logger.info("=== packages_edit.setup() called ===")

    # ==========================================================
    # Reply "Back" escape hatch for EDIT FSM
    # ==========================================================

    @router.message(F.text.in_(t_all("admin:packages:back")), PackageEdit.name)
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageEdit.description)
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageEdit.items)
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageEdit.quantity)
    async def edit_fsm_back_escape(message: Message, state: FSMContext):
        """Escape hatch: Reply Back во время Edit FSM."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.show(
            message,
            admin_packages(lang),
            title=t("admin:packages:title", lang),
            menu_context="packages",
        )

    # ==========================================================
    # EDIT MENU
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit:"))
    async def edit_menu(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        if data.get("pkg_id") != pkg_id:
            pkg = await api.get_package(pkg_id)
            await state.update_data(pkg_id=pkg_id, original=pkg, changes={})
        else:
            pkg = data.get("original") or await api.get_package(pkg_id)

        changes = dict(data.get("changes") or {})
        await state.set_state(None)

        text = build_package_edit_text(pkg, changes, lang)
        await mc.edit_inline(callback.message, text, pkg_edit_inline(pkg_id, pkg, changes, lang))
        await callback.answer()

    # ==========================================================
    # EDIT NAME
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit_name:"))
    async def edit_name_start(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(PackageEdit.name)
        await mc.edit_inline_input(callback.message, t("admin:package:enter_name", lang), pkg_edit_cancel_inline(pkg_id, lang))
        await callback.answer()

    @router.message(PackageEdit.name)
    async def edit_name_apply(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = (message.text or "").strip()
        if len(name) < 2:
            pkg_id = int((await state.get_data()).get("pkg_id") or 0)
            await mc.show_inline_input(message, t("admin:package:error_name", lang), pkg_edit_cancel_inline(pkg_id, lang))
            return

        data = await state.get_data()
        pkg_id = int(data.get("pkg_id") or 0)
        original = data.get("original") or {}
        changes: dict[str, Any] = dict(data.get("changes") or {})
        changes["name"] = name
        await state.update_data(changes=changes)
        await state.set_state(None)

        text = build_package_edit_text(original, changes, lang)
        await mc.show_inline_readonly(message, text, pkg_edit_inline(pkg_id, original, changes, lang))

    # ==========================================================
    # EDIT DESCRIPTION
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit_desc:"))
    async def edit_desc_start(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(PackageEdit.description)
        await mc.edit_inline_input(callback.message, t("admin:package:enter_description", lang), pkg_edit_clear_cancel_inline(pkg_id, lang))
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg:clear_desc:"))
    async def edit_desc_clear(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        original = data.get("original") or {}
        changes: dict[str, Any] = dict(data.get("changes") or {})
        changes["description"] = None
        await state.update_data(changes=changes)
        await state.set_state(None)

        text = build_package_edit_text(original, changes, lang)
        await mc.edit_inline(callback.message, text, pkg_edit_inline(pkg_id, original, changes, lang))
        await callback.answer()

    @router.message(PackageEdit.description)
    async def edit_desc_apply(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        desc = (message.text or "").strip()
        if desc == "" or desc.lower() in ("-", "—"):
            desc = None

        data = await state.get_data()
        pkg_id = int(data.get("pkg_id") or 0)
        original = data.get("original") or {}
        changes: dict[str, Any] = dict(data.get("changes") or {})
        changes["description"] = desc
        await state.update_data(changes=changes)
        await state.set_state(None)

        text = build_package_edit_text(original, changes, lang)
        await mc.show_inline_readonly(message, text, pkg_edit_inline(pkg_id, original, changes, lang))

    # ==========================================================
    # TOGGLE show_on_pricing / show_on_booking
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:toggle_pricing:"))
    async def toggle_pricing(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        original = data.get("original") or {}
        changes: dict[str, Any] = dict(data.get("changes") or {})
        current = changes.get("show_on_pricing", original.get("show_on_pricing", True))
        changes["show_on_pricing"] = not current
        await state.update_data(changes=changes)

        text = build_package_edit_text(original, changes, lang)
        await mc.edit_inline(callback.message, text, pkg_edit_inline(pkg_id, original, changes, lang))
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg:toggle_booking:"))
    async def toggle_booking(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        original = data.get("original") or {}
        changes: dict[str, Any] = dict(data.get("changes") or {})
        current = changes.get("show_on_booking", original.get("show_on_booking", True))
        changes["show_on_booking"] = not current
        await state.update_data(changes=changes)

        text = build_package_edit_text(original, changes, lang)
        await mc.edit_inline(callback.message, text, pkg_edit_inline(pkg_id, original, changes, lang))
        await callback.answer()

    # ==========================================================
    # EDIT ITEMS (multi-select + qty single-select)
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit_items:"))
    async def edit_items_start(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        pkg = await api.get_package(pkg_id)
        items = pkg.get("package_items") or []
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                items = []
        if isinstance(items, dict):
            items = [items]
        current_ids = set()
        if isinstance(items, list):
            for it in items:
                sid = int(it.get("service_id", 0) or 0)
                if sid > 0:
                    current_ids.add(sid)

        await state.set_state(PackageEdit.items)
        await state.update_data(
            items_selected_ids=list(current_ids),
            items_page=0,
        )

        services = await api.get_services()
        kb = pkg_items_multiselect_inline(services, current_ids, 0, lang, pkg_id)
        await mc.edit_inline(callback.message, t("admin:package:select_services", lang), kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg_edit:page:"))
    async def edit_items_page(callback: CallbackQuery, state: FSMContext):
        _, _, pkg_id_s, page_s = callback.data.split(":")
        pkg_id = int(pkg_id_s)
        page = int(page_s)
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        selected = set(data.get("items_selected_ids") or [])
        await state.update_data(items_page=page)

        services = await api.get_services()
        kb = pkg_items_multiselect_inline(services, selected, page, lang, pkg_id)
        await mc.edit_inline(callback.message, t("admin:package:select_services", lang), kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg_edit:svc:"))
    async def edit_items_toggle(callback: CallbackQuery, state: FSMContext):
        _, _, pkg_id_s, sid_s = callback.data.split(":")
        pkg_id = int(pkg_id_s)
        sid = int(sid_s)
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        selected = set(data.get("items_selected_ids") or [])
        page = int(data.get("items_page") or 0)

        if sid in selected:
            selected.remove(sid)
        else:
            selected.add(sid)

        await state.update_data(items_selected_ids=list(selected))

        services = await api.get_services()
        kb = pkg_items_multiselect_inline(services, selected, page, lang, pkg_id)
        await mc.edit_inline(callback.message, t("admin:package:select_services", lang), kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg_edit:items_done:"))
    async def edit_items_done(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        selected_ids = list(data.get("items_selected_ids") or [])
        if not selected_ids:
            await callback.answer(t("admin:package:error_no_services", lang), show_alert=True)
            return

        # transition to qty single-select
        await state.set_state(PackageEdit.quantity)
        kb = pkg_edit_qty_inline(pkg_id, lang)
        await mc.edit_inline(
            callback.message,
            t("admin:package:select_qty", lang),
            kb,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg_edit:qty:"), PackageEdit.quantity)
    async def edit_qty_select(callback: CallbackQuery, state: FSMContext):
        parts = callback.data.split(":")
        pkg_id, qty = int(parts[2]), int(parts[3])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        selected_ids = data.get("items_selected_ids") or []
        original = data.get("original") or {}
        package_items = [{"service_id": int(s), "quantity": qty} for s in selected_ids]
        changes: dict[str, Any] = dict(data.get("changes") or {})
        changes["package_items"] = json.dumps(package_items)
        await state.update_data(changes=changes)
        await state.set_state(None)

        text = build_package_edit_text(original, changes, lang)
        await mc.edit_inline(callback.message, text, pkg_edit_inline(pkg_id, original, changes, lang))
        await callback.answer()

    # ==========================================================
    # SAVE (PATCH diff)
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:save:"))
    async def save_changes(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        changes: dict[str, Any] = dict(data.get("changes") or {})

        if not changes:
            await callback.answer(t("admin:package:no_changes", lang), show_alert=True)
            return

        await api.patch_package(pkg_id, changes)
        await state.update_data(changes={})

        # reload and show updated edit menu
        pkg = await api.get_package(pkg_id)
        await state.update_data(original=pkg)

        text = t("admin:package:saved", lang) + "\n\n" + build_package_edit_text(pkg, {}, lang)
        await mc.edit_inline(callback.message, text, pkg_edit_inline(pkg_id, pkg, {}, lang))
        await callback.answer()

    @router.callback_query(F.data == "pkg_edit:noop")
    async def pkg_edit_noop(callback: CallbackQuery):
        await callback.answer()

    logger.info("=== packages_edit router configured ===")
    return router
