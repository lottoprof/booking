"""
bot/app/flows/admin/clients_sell_package.py

Продажа пакета клиенту из карточки клиента.
"""

import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


# ==============================================================
# Helpers
# ==============================================================

def _format_name(user: dict) -> str:
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


def _format_price(price: float, lang: str) -> str:
    currency = t("currency", lang)
    return f"{price:,.0f} {currency}".replace(",", " ")


# ==============================================================
# Keyboards
# ==============================================================

def kb_packages_list(packages: list, page: int, total: int, user_id: int, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for pkg in packages:
        name = pkg.get("name", "—")
        price = _format_price(pkg.get("package_price", 0), lang)
        rows.append([InlineKeyboardButton(
            text=f"📦 {name} ({price})",
            callback_data=f"sellpkg:select:{user_id}:{pkg['id']}"
        )])

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sellpkg:page:{user_id}:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="sellpkg:noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sellpkg:page:{user_id}:{page+1}"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(text=t("common:back", lang), callback_data=f"client:view:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_validity_select(user_id: int, package_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:sellpkg:days_60", lang), callback_data=f"sellpkg:valid:{user_id}:{package_id}:60"),
            InlineKeyboardButton(text=t("admin:sellpkg:days_90", lang), callback_data=f"sellpkg:valid:{user_id}:{package_id}:90"),
            InlineKeyboardButton(text=t("admin:sellpkg:days_180", lang), callback_data=f"sellpkg:valid:{user_id}:{package_id}:180"),
        ],
        [InlineKeyboardButton(text=t("common:back", lang), callback_data=f"sellpkg:start:{user_id}")]
    ])


def kb_confirm(user_id: int, package_id: int, days: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:sellpkg:sell", lang), callback_data=f"sellpkg:confirm:{user_id}:{package_id}:{days}"),
            InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"client:view:{user_id}"),
        ]
    ])


# ==============================================================
# Setup
# ==============================================================

def setup(menu_controller, api):
    router = Router(name="clients_sell_package")
    mc = menu_controller

    # ----------------------------------------------------------
    # Callback: начало продажи — список пакетов
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("sellpkg:start:"))
    async def start_sell(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])

        packages = await api.get_packages()
        if not packages:
            await callback.answer(t("admin:sellpkg:empty", lang), show_alert=True)
            return

        await state.update_data(sellpkg_user_id=user_id, sellpkg_packages=packages, sellpkg_page=0)

        text = t("admin:sellpkg:title", lang)
        kb = kb_packages_list(packages[:PAGE_SIZE], 0, len(packages), user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: пагинация пакетов
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("sellpkg:page:"))
    async def paginate_packages(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])

        data = await state.get_data()
        packages = data.get("sellpkg_packages", [])
        await state.update_data(sellpkg_page=page)

        start = page * PAGE_SIZE
        text = t("admin:sellpkg:title", lang)
        kb = kb_packages_list(packages[start:start+PAGE_SIZE], page, len(packages), user_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "sellpkg:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: выбор пакета — выбор срока действия
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("sellpkg:select:"))
    async def select_package(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        package_id = int(parts[3])

        package = await api.get_package(package_id)
        user = await api.get_user(user_id)

        if not package or not user:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        await state.update_data(sellpkg_package_id=package_id)

        name = _format_name(user)
        lines = [
            t("admin:sellpkg:package", lang, package.get("name", "—")),
            t("admin:sellpkg:price", lang, _format_price(package.get("package_price", 0), lang)),
            t("admin:sellpkg:client", lang, name),
            "",
            t("admin:sellpkg:validity", lang),
        ]

        kb = kb_validity_select(user_id, package_id, lang)
        await mc.edit_inline(callback.message, "\n".join(lines), kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: выбор срока — подтверждение
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("sellpkg:valid:"))
    async def select_validity(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        package_id = int(parts[3])
        days = int(parts[4])

        package = await api.get_package(package_id)
        user = await api.get_user(user_id)

        if not package or not user:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        await state.update_data(sellpkg_days=days)

        name = _format_name(user)

        valid_to = (datetime.utcnow() + timedelta(days=days)).strftime("%d.%m.%Y")
        validity_text = f"до {valid_to}"

        lines = [
            t("admin:sellpkg:confirm", lang),
            "",
            t("admin:sellpkg:package", lang, package.get("name", "—")),
            t("admin:sellpkg:price", lang, _format_price(package.get("package_price", 0), lang)),
            t("admin:sellpkg:client", lang, name),
            f"📅 {validity_text}",
        ]

        kb = kb_confirm(user_id, package_id, days, lang)
        await mc.edit_inline(callback.message, "\n".join(lines), kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Callback: подтверждение продажи
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("sellpkg:confirm:"))
    async def confirm_sell(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        package_id = int(parts[3])
        days = int(parts[4])

        # Calculate valid_to
        valid_to = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        # Create client package
        result = await api.create_client_package(
            user_id=user_id,
            package_id=package_id,
            valid_to=valid_to,
        )

        if result:
            await callback.answer(t("admin:sellpkg:sold", lang), show_alert=True)
        else:
            await callback.answer(t("admin:sellpkg:error", lang), show_alert=True)
            return

        # Return to client card
        user = await api.get_user(user_id)
        if not user:
            await callback.answer()
            return

        from bot.app.flows.admin.clients_find import kb_client_card, _format_name, _format_phone, _format_date, _format_balance, _role_name

        name = _format_name(user)
        stats = await api.get_user_stats(user_id) or {}
        wallet = await api.get_wallet(user_id) or {}
        roles = await api.get_user_roles(user_id)

        role_id = min((r.get("role_id", 4) for r in roles), default=4) if roles else 4

        lines = [
            t("admin:client:card_title", lang, name),
            "",
            _format_phone(user.get("phone"), lang),
            t("admin:client:registered", lang, _format_date(user.get("created_at"))),
            t("admin:client:bookings_count", lang, stats.get("total_bookings", 0)),
            t("admin:client:balance", lang, _format_balance(wallet.get("balance", 0), lang)),
            t("admin:client:role", lang, _role_name(role_id, lang)),
        ]

        await mc.edit_inline(callback.message, "\n".join(lines), kb_client_card(user_id, lang))
        await callback.answer()

    return router
