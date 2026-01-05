"""
bot/app/flows/admin/packages.py

Service Packages (admin):
- LIST (inline, pagination)
- VIEW
- DELETE (soft-delete via API DELETE)
- CREATE (FSM, Redis) — name/description -> select services -> quantities -> price
- EDIT делегирован в packages_edit.py

Важно:
- Бот не содержит бизнес-логики, работает строго через API.md
- Создание/редактирование пакета НЕ валидирует специалистов (по решению)
"""

import logging
import math
from typing import Any

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.keyboards.admin import admin_packages  # reply keyboard entry (как admin_specialists)

# EDIT entry point
from .packages_edit import start_package_edit, setup as setup_edit

logger = logging.getLogger(__name__)

PAGE_SIZE = 5
SERVICES_PAGE_SIZE = 8


# ==============================================================
# FSM: CREATE
# ==============================================================

class PackageCreate(StatesGroup):
    name = State()
    description = State()
    services = State()   # multi-select
    quantity = State()   # sequential input per service
    price = State()


# ==============================================================
# Helpers
# ==============================================================

def _safe_decimal(text: str) -> float | None:
    """
    Accepts: "12000", "12000.50", "12000,50"
    Returns float or None.
    """
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


def pkg_cancel_inline(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("common:cancel", lang), callback_data="pkg_create:cancel")
    ]])


def pkg_skip_inline(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("common:skip", lang), callback_data="pkg_create:skip")],
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data="pkg_create:cancel")],
    ])


def packages_list_inline(packages: list[dict], page: int, lang: str) -> InlineKeyboardMarkup:
    total = len(packages)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, pages - 1))

    start = page * PAGE_SIZE
    chunk = packages[start:start + PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for p in chunk:
        rows.append([
            InlineKeyboardButton(
                text=t("admin:packages:item", lang) % (p.get("name") or "?"),
                callback_data=f"pkg:view:{p['id']}"
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if pages > 1:
        if page > 0:
            nav.append(InlineKeyboardButton(text=t("common:prev", lang), callback_data=f"pkg:page:{page-1}"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text=t("common:next", lang), callback_data=f"pkg:page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("common:back", lang), callback_data="pkg:back")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def package_view_inline(pkg_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:package:edit", lang), callback_data=f"pkg:edit:{pkg_id}"),
            InlineKeyboardButton(text=t("admin:package:delete", lang), callback_data=f"pkg:delete:{pkg_id}"),
        ],
        [
            InlineKeyboardButton(text=t("admin:package:back", lang), callback_data="pkg:list:0"),
        ]
    ])


def pkg_create_services_inline(
    services: list[dict],
    selected_ids: set[int],
    page: int,
    lang: str
) -> InlineKeyboardMarkup:
    total = len(services)
    pages = max(1, math.ceil(total / SERVICES_PAGE_SIZE))
    page = max(0, min(page, pages - 1))

    start = page * SERVICES_PAGE_SIZE
    chunk = services[start:start + SERVICES_PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []

    for s in chunk:
        sid = int(s["id"])
        name = s.get("name") or "?"
        mark = "✅ " if sid in selected_ids else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{mark}{name}",
                callback_data=f"pkg_create:svc:{sid}"
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if pages > 1:
        if page > 0:
            nav.append(InlineKeyboardButton(text=t("common:prev", lang), callback_data=f"pkg_create:page:{page-1}"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text=t("common:next", lang), callback_data=f"pkg_create:page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(
            text=t("admin:package:services_selected", lang) % len(selected_ids),
            callback_data="pkg_create:services_done"
        ),
        InlineKeyboardButton(text=t("common:cancel", lang), callback_data="pkg_create:cancel"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==============================================================
# Text render
# ==============================================================

async def render_package_view(pkg: dict, lang: str) -> str:
    name = pkg.get("name") or "?"
    lines: list[str] = [t("admin:package:view_title", lang) % name, ""]

    if pkg.get("description"):
        lines.append(t("admin:package:description", lang) % pkg["description"])
        lines.append("")

    # items
    lines.append(t("admin:package:items_title", lang))

    services = await api.get_services()
    services_map = {int(s["id"]): (s.get("name") or "?") for s in services}

    items = pkg.get("package_items") or []
    # backend может вернуть JSON как строку — не трогаем тут (в v1 ожидаем list)
    if isinstance(items, dict):
        items = [items]

    if isinstance(items, list) and items:
        for it in items:
            sid = int(it.get("service_id", 0) or 0)
            qty = int(it.get("quantity", 0) or 0)
            svc_name = services_map.get(sid, "?")
            lines.append(t("admin:package:item_row", lang) % (svc_name, qty))
    else:
        lines.append("• ?")

    lines.append("")
    price = pkg.get("package_price")
    price_str = str(price) if price is not None else "0"
    lines.append(t("admin:package:price", lang) % price_str)

    return "\n".join(lines)


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    router = Router(name="packages")
    logger.info("=== packages.setup() called ===")

    # register edit router
    edit_router = setup_edit(mc, get_user_role)

    # ==========================================================
    # LIST
    # ==========================================================

    async def show_list(message: Message, page: int = 0):
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)

        packages = await api.get_packages()
        total = len(packages)

        if total == 0:
            text = f"📦 {t('admin:packages:empty', lang)}"
        else:
            text = t("admin:packages:list_title", lang) % total

        kb = packages_list_inline(packages, page, lang)
        await mc.show_inline_readonly(message, text, kb)

    router.show_list = show_list

    @router.callback_query(F.data.startswith("pkg:page:"))
    async def list_page(callback: CallbackQuery):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        packages = await api.get_packages()
        total = len(packages)

        if total == 0:
            text = f"📦 {t('admin:packages:empty', lang)}"
        else:
            text = t("admin:packages:list_title", lang) % total

        kb = packages_list_inline(packages, page, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "pkg:list:0")
    async def list_first_page(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        packages = await api.get_packages()
        total = len(packages)

        if total == 0:
            text = f"📦 {t('admin:packages:empty', lang)}"
        else:
            text = t("admin:packages:list_title", lang) % total

        kb = packages_list_inline(packages, 0, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "pkg:back")
    async def back_to_reply(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await mc.back_to_reply(callback.message, t("admin:packages:title", lang), admin_packages(lang))
        await callback.answer()

    # ==========================================================
    # VIEW
    # ==========================================================

    async def show_view(message: Message, pkg_id: int):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        pkg = await api.get_package(pkg_id)
        text = await render_package_view(pkg, lang)
        kb = package_view_inline(pkg_id, lang)
        await mc.show_inline_readonly(message, text, kb)

    router.show_view = show_view

    @router.callback_query(F.data.startswith("pkg:view:"))
    async def view_pkg(callback: CallbackQuery):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        pkg = await api.get_package(pkg_id)
        text = await render_package_view(pkg, lang)
        kb = package_view_inline(pkg_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ==========================================================
    # DELETE
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:delete:"))
    async def delete_confirm(callback: CallbackQuery):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        # confirm screen
        pkg = await api.get_package(pkg_id)
        name = pkg.get("name") or "?"
        text = t("admin:package:confirm_delete", lang) % name + "\n\n" + t("admin:package:delete_warning", lang)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=t("common:yes", lang), callback_data=f"pkg:delete_yes:{pkg_id}"),
                InlineKeyboardButton(text=t("common:no", lang), callback_data=f"pkg:view:{pkg_id}"),
            ]
        ])
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg:delete_yes:"))
    async def delete_yes(callback: CallbackQuery):
        pkg_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await api.delete_package(pkg_id)

        # back to list
        packages = await api.get_packages()
        total = len(packages)
        if total == 0:
            text = f"📦 {t('admin:packages:empty', lang)}"
        else:
            text = t("admin:packages:list_title", lang) % total

        kb = packages_list_inline(packages, 0, lang)
        await mc.edit_inline(callback.message, t("admin:package:deleted", lang) + "\n\n" + text, kb)
        await callback.answer()

    # ==========================================================
    # CREATE (FSM)
    # ==========================================================

    async def start_create(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)

        await state.clear()
        await state.set_state(PackageCreate.name)
        await mc.show_inline_input(
            message,
            t("admin:package:enter_name", lang),
            pkg_cancel_inline(lang)
        )

    router.start_create = start_create

    @router.callback_query(F.data == "pkg_create:cancel")
    async def create_cancel(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await mc.back_to_reply(callback.message, t("admin:packages:title", lang), admin_packages(lang))
        await callback.answer()

    @router.message(PackageCreate.name)
    async def create_name(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = (message.text or "").strip()
        if len(name) < 2:
            await mc.show_inline_input(message, t("admin:package:error_name", lang), pkg_cancel_inline(lang))
            return

        await state.update_data(name=name)
        await state.set_state(PackageCreate.description)
        await mc.show_inline_input(
            message,
            t("admin:package:enter_description", lang),
            pkg_skip_inline(lang)
        )

    @router.callback_query(F.data == "pkg_create:skip")
    async def create_desc_skip(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.update_data(description=None)
        await state.set_state(PackageCreate.services)

        services = await api.get_services()
        selected_ids: set[int] = set()
        await state.update_data(selected_ids=list(selected_ids), svc_page=0)

        kb = pkg_create_services_inline(services, selected_ids, 0, lang)
        await mc.edit_inline(callback.message, t("admin:package:select_services", lang), kb)
        await callback.answer()

    @router.message(PackageCreate.description)
    async def create_desc(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        desc = (message.text or "").strip()
        # allow empty -> None
        if desc == "" or desc.lower() in ("-", "—"):
            desc = None

        await state.update_data(description=desc)
        await state.set_state(PackageCreate.services)

        services = await api.get_services()
        selected_ids: set[int] = set()
        await state.update_data(selected_ids=list(selected_ids), svc_page=0)

        kb = pkg_create_services_inline(services, selected_ids, 0, lang)
        await mc.show_inline_readonly(message, t("admin:package:select_services", lang), kb)

    @router.callback_query(F.data.startswith("pkg_create:page:"))
    async def create_services_page(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        page = int(callback.data.split(":")[2])

        data = await state.get_data()
        selected_ids = set(data.get("selected_ids") or [])

        services = await api.get_services()
        kb = pkg_create_services_inline(services, selected_ids, page, lang)
        await state.update_data(svc_page=page)

        await mc.edit_inline(callback.message, t("admin:package:select_services", lang), kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg_create:svc:"))
    async def create_services_toggle(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        sid = int(callback.data.split(":")[2])

        data = await state.get_data()
        selected_ids = set(data.get("selected_ids") or [])
        page = int(data.get("svc_page") or 0)

        if sid in selected_ids:
            selected_ids.remove(sid)
        else:
            selected_ids.add(sid)

        await state.update_data(selected_ids=list(selected_ids))

        services = await api.get_services()
        kb = pkg_create_services_inline(services, selected_ids, page, lang)
        await mc.edit_inline(callback.message, t("admin:package:select_services", lang), kb)
        await callback.answer()

    @router.callback_query(F.data == "pkg_create:services_done")
    async def create_services_done(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        selected_ids = list(data.get("selected_ids") or [])
        if not selected_ids:
            await callback.answer(t("admin:package:error_no_services", lang), show_alert=True)
            return

        # prepare quantity sequence
        await state.set_state(PackageCreate.quantity)
        await state.update_data(q_service_ids=selected_ids, q_index=0, quantities={})

        services = await api.get_services()
        services_map = {int(s["id"]): (s.get("name") or "?") for s in services}
        first_id = int(selected_ids[0])
        svc_name = services_map.get(first_id, "?")

        await mc.edit_inline_input(
            callback.message,
            t("admin:package:enter_quantity", lang) % svc_name,
            pkg_cancel_inline(lang)
        )
        await callback.answer()

    @router.message(PackageCreate.quantity)
    async def create_quantity(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        qty = _safe_int(message.text or "")
        if qty is None:
            await mc.show_inline_input(message, t("admin:package:error_quantity", lang), pkg_cancel_inline(lang))
            return

        data = await state.get_data()
        ids = list(data.get("q_service_ids") or [])
        idx = int(data.get("q_index") or 0)
        quantities: dict[str, Any] = dict(data.get("quantities") or {})

        if idx < 0 or idx >= len(ids):
            # safety
            await state.clear()
            await mc.back_to_reply(message, t("common:error", lang), admin_packages(lang))
            return

        sid = int(ids[idx])
        quantities[str(sid)] = qty

        idx += 1
        await state.update_data(quantities=quantities, q_index=idx)

        if idx >= len(ids):
            # go to price
            await state.set_state(PackageCreate.price)
            await mc.show_inline_input(
                message,
                t("admin:package:enter_price", lang),
                pkg_cancel_inline(lang)
            )
            return

        services = await api.get_services()
        services_map = {int(s["id"]): (s.get("name") or "?") for s in services}
        next_id = int(ids[idx])
        next_name = services_map.get(next_id, "?")

        await mc.show_inline_input(
            message,
            t("admin:package:enter_quantity", lang) % next_name,
            pkg_cancel_inline(lang)
        )

    @router.message(PackageCreate.price)
    async def create_price(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        price = _safe_decimal(message.text or "")
        if price is None:
            await mc.show_inline_input(message, t("admin:package:error_price", lang), pkg_cancel_inline(lang))
            return

        data = await state.get_data()
        name = data.get("name")
        description = data.get("description")
        ids = list(data.get("q_service_ids") or [])
        quantities = dict(data.get("quantities") or {})

        package_items = []
        for sid in ids:
            q = int(quantities.get(str(sid), 1))
            package_items.append({"service_id": int(sid), "quantity": q})

        payload = {
            "name": name,
            "description": description,
            "package_items": package_items,
            "package_price": round(price, 2),
        }

        created = await api.create_package(payload)
        await state.clear()

        # show created view
        pkg_id = int(created["id"])
        pkg = await api.get_package(pkg_id)
        text = t("admin:package:created", lang) % (pkg.get("name") or "?")
        view_text = await render_package_view(pkg, lang)
        kb = package_view_inline(pkg_id, lang)

        await mc.show_inline_readonly(message, text + "\n\n" + view_text, kb)

    # ==========================================================
    # EDIT (delegate)
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit:"))
    async def edit_from_view(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        await start_package_edit(callback, state, pkg_id)
        await callback.answer()

    return router, edit_router

