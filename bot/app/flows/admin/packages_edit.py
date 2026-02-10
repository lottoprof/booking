"""
bot/app/flows/admin/packages_edit.py

EDIT-FSM for Service Packages (admin).

Правила:
- FSM в Redis (aiogram storage)
- PATCH только diff (changes)
- Inline-only
- Не управляет Reply/menu_context (это делает packages.py)

Особенности:
- Редактирование состава: multi-select услуг + ввод quantity для каждой выбранной услуги
- Можно сохранить без description (None)
"""

import json
import logging
import math
from typing import Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, t_all, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.keyboards.admin import admin_packages

logger = logging.getLogger(__name__)

PAGE_SIZE = 8


# ==============================================================
# FSM States (EDIT)
# ==============================================================

class PackageEdit(StatesGroup):
    name = State()
    description = State()
    items = State()       # multi-select
    quantity = State()    # sequential input per service
    price = State()


# ==============================================================
# Helpers
# ==============================================================

def _safe_decimal(text: str) -> float | None:
    if text is None:
        return None
    s = text.strip().replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        val = float(s)
        if val < 0:
            return None
        return val
    except Exception:
        return None


def _safe_int(text: str) -> int | None:
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None
    try:
        v = int(s)
        if v <= 0:
            return None
        return v
    except Exception:
        return None


def pkg_edit_inline(pkg_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:package:edit_name", lang), callback_data=f"pkg:edit_name:{pkg_id}"),
            InlineKeyboardButton(text=t("admin:package:edit_description", lang), callback_data=f"pkg:edit_desc:{pkg_id}"),
        ],
        [
            InlineKeyboardButton(text=t("admin:package:edit_services", lang), callback_data=f"pkg:edit_items:{pkg_id}"),
            InlineKeyboardButton(text=t("admin:package:edit_price", lang), callback_data=f"pkg:edit_price:{pkg_id}"),
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

    nav: list[InlineKeyboardButton] = []
    if pages > 1:
        if page > 0:
            nav.append(InlineKeyboardButton(text=t("common:prev", lang), callback_data=f"pkg_edit:page:{pkg_id}:{page-1}"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text=t("common:next", lang), callback_data=f"pkg_edit:page:{pkg_id}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text=t("admin:package:services_selected", lang) % len(selected_ids), callback_data=f"pkg_edit:items_done:{pkg_id}"),
        InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"pkg:edit:{pkg_id}"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==============================================================
# Public entry
# ==============================================================

async def start_package_edit(callback: CallbackQuery, state: FSMContext, pkg_id: int):
    lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

    await state.clear()
    await state.update_data(pkg_id=pkg_id, changes={})

    # show edit menu
    await state.set_state(None)  # menu state-free (как в specialists_edit)
    await callback.message.edit_text(t("admin:package:edit_title", lang), reply_markup=pkg_edit_inline(pkg_id, lang))


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
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageEdit.price)
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
            await state.update_data(pkg_id=pkg_id, changes={})

        await callback.message.edit_text(t("admin:package:edit_title", lang), reply_markup=pkg_edit_inline(pkg_id, lang))
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
        changes: dict[str, Any] = dict(data.get("changes") or {})
        changes["name"] = name
        await state.update_data(changes=changes)
        await state.set_state(None)

        await mc.show_inline_readonly(message, t("admin:package:edit_title", lang), pkg_edit_inline(pkg_id, lang))

    # ==========================================================
    # EDIT DESCRIPTION
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit_desc:"))
    async def edit_desc_start(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(PackageEdit.description)
        await mc.edit_inline_input(callback.message, t("admin:package:enter_description", lang), pkg_edit_cancel_inline(pkg_id, lang))
        await callback.answer()

    @router.message(PackageEdit.description)
    async def edit_desc_apply(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        desc = (message.text or "").strip()
        if desc == "" or desc.lower() in ("-", "—"):
            desc = None

        data = await state.get_data()
        pkg_id = int(data.get("pkg_id") or 0)
        changes: dict[str, Any] = dict(data.get("changes") or {})
        changes["description"] = desc
        await state.update_data(changes=changes)
        await state.set_state(None)

        await mc.show_inline_readonly(message, t("admin:package:edit_title", lang), pkg_edit_inline(pkg_id, lang))

    # ==========================================================
    # EDIT PRICE
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit_price:"))
    async def edit_price_start(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(PackageEdit.price)
        await mc.edit_inline_input(callback.message, t("admin:package:enter_price", lang), pkg_edit_cancel_inline(pkg_id, lang))
        await callback.answer()

    @router.message(PackageEdit.price)
    async def edit_price_apply(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        price = _safe_decimal(message.text or "")
        if price is None:
            pkg_id = int((await state.get_data()).get("pkg_id") or 0)
            await mc.show_inline_input(message, t("admin:package:error_price", lang), pkg_edit_cancel_inline(pkg_id, lang))
            return

        data = await state.get_data()
        pkg_id = int(data.get("pkg_id") or 0)
        changes: dict[str, Any] = dict(data.get("changes") or {})
        changes["package_price"] = round(price, 2)
        await state.update_data(changes=changes)
        await state.set_state(None)

        await mc.show_inline_readonly(message, t("admin:package:edit_title", lang), pkg_edit_inline(pkg_id, lang))

    # ==========================================================
    # EDIT ITEMS (multi-select + quantities)
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit_items:"))
    async def edit_items_start(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        pkg = await api.get_package(pkg_id)
        items = pkg.get("package_items") or []
        if isinstance(items, dict):
            items = [items]
        current_ids = set()
        current_qty: dict[int, int] = {}
        if isinstance(items, list):
            for it in items:
                sid = int(it.get("service_id", 0) or 0)
                qty = int(it.get("quantity", 0) or 0)
                if sid > 0 and qty > 0:
                    current_ids.add(sid)
                    current_qty[sid] = qty

        await state.set_state(PackageEdit.items)
        await state.update_data(
            items_selected_ids=list(current_ids),
            items_page=0,
            items_current_qty={str(k): v for k, v in current_qty.items()},
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

        # sequential quantities
        await state.set_state(PackageEdit.quantity)
        current_qty = dict(data.get("items_current_qty") or {})

        await state.update_data(
            q_service_ids=selected_ids,
            q_index=0,
            q_quantities=current_qty,  # str->int
        )

        services = await api.get_services()
        services_map = {int(s["id"]): (s.get("name") or "?") for s in services}
        first_id = int(selected_ids[0])
        svc_name = services_map.get(first_id, "?")

        await mc.edit_inline_input(
            callback.message,
            t("admin:package:enter_quantity", lang) % svc_name,
            pkg_edit_cancel_inline(pkg_id, lang)
        )
        await callback.answer()

    @router.message(PackageEdit.quantity)
    async def edit_items_quantity(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        qty = _safe_int(message.text or "")
        if qty is None:
            pkg_id = int((await state.get_data()).get("pkg_id") or 0)
            await mc.show_inline_input(message, t("admin:package:error_quantity", lang), pkg_edit_cancel_inline(pkg_id, lang))
            return

        data = await state.get_data()
        pkg_id = int(data.get("pkg_id") or 0)
        ids = list(data.get("q_service_ids") or [])
        idx = int(data.get("q_index") or 0)
        q_quantities: dict[str, Any] = dict(data.get("q_quantities") or {})

        if idx < 0 or idx >= len(ids):
            await state.set_state(None)
            await mc.show_inline_readonly(message, t("admin:package:edit_title", lang), pkg_edit_inline(pkg_id, lang))
            return

        sid = int(ids[idx])
        q_quantities[str(sid)] = qty

        idx += 1
        await state.update_data(q_quantities=q_quantities, q_index=idx)

        if idx >= len(ids):
            # finalize package_items change
            package_items = []
            for s in ids:
                q = int(q_quantities.get(str(int(s)), 1))
                package_items.append({"service_id": int(s), "quantity": q})

            changes: dict[str, Any] = dict(data.get("changes") or {})
            changes["package_items"] = json.dumps(package_items)
            await state.update_data(changes=changes)
            await state.set_state(None)

            await mc.show_inline_readonly(message, t("admin:package:edit_title", lang), pkg_edit_inline(pkg_id, lang))
            return

        services = await api.get_services()
        services_map = {int(s["id"]): (s.get("name") or "?") for s in services}
        next_id = int(ids[idx])
        next_name = services_map.get(next_id, "?")

        await mc.show_inline_input(
            message,
            t("admin:package:enter_quantity", lang) % next_name,
            pkg_edit_cancel_inline(pkg_id, lang)
        )

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

        # back to view
        await callback.message.edit_text(t("admin:package:saved", lang), reply_markup=pkg_edit_inline(pkg_id, lang))
        await callback.answer()

    logger.info("=== packages_edit router configured ===")
    return router

