"""
bot/app/flows/admin/packages.py

Service Packages (admin):
- LIST (inline, pagination)
- VIEW
- DELETE (soft-delete via API DELETE)
- CREATE (FSM, Redis) — name/description -> select services -> quantities multi-select [1][5][10]
- EDIT делегирован в packages_edit.py

Важно:
- Бот не содержит бизнес-логики, работает строго через API.md
- Создание/редактирование пакета НЕ валидирует специалистов (по решению)
- quantity — per-package-variant, все сервисы получают одинаковый qty
- price вычисляется динамически (не вводится)
"""

import json
import logging
import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.app.i18n.loader import DEFAULT_LANG, t, t_all
from bot.app.keyboards.admin import admin_packages
from bot.app.utils.api import api
from bot.app.utils.pagination import build_nav_row
from bot.app.utils.state import user_lang

from .packages_edit import setup as setup_edit

# EDIT entry point
from .packages_edit import start_package_edit

logger = logging.getLogger(__name__)

PAGE_SIZE = 5
SERVICES_PAGE_SIZE = 8


# ==============================================================
# FSM: CREATE
# ==============================================================

class PackageCreate(StatesGroup):
    name = State()
    description = State()
    services = State()       # multi-select сервисов
    quantities = State()     # multi-select qty [1][5][10]


# ==============================================================
# Helpers
# ==============================================================

def pkg_cancel_inline(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("common:cancel", lang), callback_data="pkg_create:cancel")
    ]])


def pkg_skip_inline(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("common:skip", lang), callback_data="pkg_create:skip")],
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data="pkg_create:cancel")],
    ])


def _format_pkg_item(pkg: dict) -> str:
    """Compact list item: 📦 name | ×5 | 9000."""
    name = pkg.get("name") or "?"
    items = pkg.get("package_items") or "[]"
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []
    qty = items[0].get("quantity", 1) if isinstance(items, list) and items else 1
    price = pkg.get("package_price")
    if price is not None:
        price_val = float(price)
        price_str = str(int(price_val)) if price_val == int(price_val) else str(price_val)
    else:
        price_str = "0"
    return f"📦 {name} | ×{qty} | {price_str}"


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
                text=_format_pkg_item(p),
                callback_data=f"pkg:view:{p['id']}"
            )
        ])

    nav = build_nav_row(page, pages, "pkg:page:{p}", "pkg:noop", lang)
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

    nav = build_nav_row(page, pages, "pkg_create:page:{p}", "pkg_create:noop", lang)
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


def pkg_qty_multiselect_inline(selected_qtys: set[int], lang: str) -> InlineKeyboardMarkup:
    """Multi-select: [✅1] [5] [✅10] + [Готово N] [Отмена]."""
    qty_row = []
    for q in (1, 5, 10):
        mark = "✅ " if q in selected_qtys else ""
        qty_row.append(InlineKeyboardButton(
            text=f"{mark}{q}",
            callback_data=f"pkg_create:qty:{q}"
        ))
    return InlineKeyboardMarkup(inline_keyboard=[
        qty_row,
        [
            InlineKeyboardButton(
                text=t("admin:package:qty_done", lang) % len(selected_qtys),
                callback_data="pkg_create:qty_done"
            ),
            InlineKeyboardButton(text=t("common:cancel", lang), callback_data="pkg_create:cancel"),
        ],
    ])


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

    # Если items — строка (JSON), парсим её
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []

    # backend может вернуть dict вместо list
    if isinstance(items, dict):
        items = [items]

    if isinstance(items, list) and items:
        for it in items:
            sid = int(it.get("service_id", 0) or 0)
            qty = int(it.get("quantity", 0) or 0)
            svc_name = services_map.get(sid, "?")
            lines.append(t("admin:package:item_row", lang) % (svc_name, qty))

    lines.append("")
    price = pkg.get("package_price")
    price_str = str(price) if price is not None else "0"
    lines.append(t("admin:package:price", lang) % price_str)

    # show_on flags
    p = "✅" if pkg.get("show_on_pricing") else "❌"
    b = "✅" if pkg.get("show_on_booking") else "❌"
    lines.append(f"📊 pricing: {p} | booking: {b}")

    return "\n".join(lines)

# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    router = Router(name="packages")
    logger.info("=== packages.setup() called ===")

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
    async def back_to_reply_menu(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await mc.back_to_reply(
            callback.message,
            admin_packages(lang),
            title=t("admin:packages:title", lang),
            menu_context="packages",
        )
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

    # ---- Reply "Back" button во время FSM (escape hatch)
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageCreate.name)
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageCreate.description)
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageCreate.services)
    @router.message(F.text.in_(t_all("admin:packages:back")), PackageCreate.quantities)
    async def fsm_back_escape(message: Message, state: FSMContext):
        """Escape hatch: Reply Back во время FSM → отмена и возврат в меню."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.show(
            message,
            admin_packages(lang),
            title=t("admin:packages:title", lang),
            menu_context="packages",
        )

    @router.callback_query(F.data == "pkg_create:cancel")
    async def create_cancel(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await mc.back_to_reply(
            callback.message,
            admin_packages(lang),
            title=t("admin:packages:title", lang),
            menu_context="packages",
        )
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

        # transition to quantities multi-select
        await state.set_state(PackageCreate.quantities)
        await state.update_data(selected_qtys=[])

        kb = pkg_qty_multiselect_inline(set(), lang)
        await mc.edit_inline(
            callback.message,
            t("admin:package:select_quantities", lang),
            kb,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("pkg_create:qty:"), PackageCreate.quantities)
    async def create_qty_toggle(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        qty = int(callback.data.split(":")[2])

        data = await state.get_data()
        selected = set(data.get("selected_qtys") or [])
        if qty in selected:
            selected.discard(qty)
        else:
            selected.add(qty)
        await state.update_data(selected_qtys=list(selected))

        kb = pkg_qty_multiselect_inline(selected, lang)
        await mc.edit_inline(
            callback.message,
            t("admin:package:select_quantities", lang),
            kb,
        )
        await callback.answer()

    @router.callback_query(F.data == "pkg_create:qty_done", PackageCreate.quantities)
    async def create_qty_done(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        selected_qtys = sorted(data.get("selected_qtys") or [])
        if not selected_qtys:
            await callback.answer(t("admin:package:error_no_qty", lang), show_alert=True)
            return

        name = data.get("name")
        description = data.get("description")
        selected_ids = list(data.get("selected_ids") or [])

        # Получаем company_id
        company = await api.get_company()
        if not company:
            await state.clear()
            await mc.back_to_reply(
                callback.message,
                admin_packages(lang),
                title=t("common:error", lang),
                menu_context="packages",
            )
            await callback.answer()
            return

        # Create N rows — one per selected qty
        last_created = None
        for qty in selected_qtys:
            package_items = [{"service_id": int(sid), "quantity": qty} for sid in selected_ids]
            payload = {
                "company_id": company["id"],
                "name": name,
                "description": description,
                "package_items": json.dumps(package_items),
            }
            last_created = await api.create_package(payload)

        await state.clear()

        if not last_created:
            await mc.back_to_reply(
                callback.message,
                admin_packages(lang),
                title=t("common:error", lang),
                menu_context="packages",
            )
            await callback.answer()
            return

        # show list after creation
        packages = await api.get_packages()
        total = len(packages)
        header = t("admin:package:created", lang) % (name or "?")
        if total == 0:
            text = f"📦 {t('admin:packages:empty', lang)}"
        else:
            text = t("admin:packages:list_title", lang) % total

        kb = packages_list_inline(packages, 0, lang)
        await mc.edit_inline(callback.message, header + "\n\n" + text, kb)
        await callback.answer()

    # ==========================================================
    # Noop (disabled pagination buttons)
    # ==========================================================

    @router.callback_query(F.data == "pkg:noop")
    async def pkg_noop(callback: CallbackQuery):
        await callback.answer()

    @router.callback_query(F.data == "pkg_create:noop")
    async def pkg_create_noop(callback: CallbackQuery):
        await callback.answer()

    # ==========================================================
    # EDIT (delegate)
    # ==========================================================

    @router.callback_query(F.data.startswith("pkg:edit:"))
    async def edit_from_view(callback: CallbackQuery, state: FSMContext):
        pkg_id = int(callback.data.split(":")[2])
        await start_package_edit(mc, callback, state, pkg_id)
        await callback.answer()

    # подключаем EDIT router
    router.include_router(setup_edit(mc, get_user_role))

    logger.info("=== packages router configured ===")
    return router
