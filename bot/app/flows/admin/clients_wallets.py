"""
bot/app/flows/admin/clients_wallets.py

Кошелёк клиента: пополнение, списание, история.
"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.utils.pagination import build_nav_row
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 10


class WalletOp(StatesGroup):
    deposit_amount = State()
    deposit_comment = State()
    withdraw_amount = State()
    withdraw_comment = State()


# ==============================================================
# Helpers
# ==============================================================

def _format_name(user: dict) -> str:
    first = user.get("first_name", "")
    last = user.get("last_name", "")
    return f"{last} {first}".strip() if last else (first or "—")


def _format_balance(balance: float, lang: str) -> str:
    currency = t("currency", lang)
    return f"{balance:,.0f} {currency}".replace(",", " ")


def parse_amount(text: str) -> float | None:
    """Парсит сумму. Возвращает float > 0 или None."""
    try:
        text = text.replace(",", ".").replace(" ", "").replace("₽", "").replace("$", "")
        amount = float(text)
        return amount if amount > 0 else None
    except ValueError:
        return None


def _format_tx(tx: dict, lang: str) -> str:
    """Форматирует одну транзакцию."""
    amount = tx.get("amount", 0)
    tx_type = tx.get("type", "")
    created = tx.get("created_at", "")
    desc = tx.get("description", "")
    
    # Знак
    sign = "+" if amount > 0 else ""
    
    # Тип
    type_key = f"admin:wallet:tx_{tx_type}"
    type_name = t(type_key, lang)
    if type_name == type_key:
        type_name = tx_type
    
    # Дата
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        date_str = dt.strftime("%d.%m %H:%M")
    except Exception:
        date_str = created[:16] if created else ""
    
    currency = t("currency", lang)
    line = f"{sign}{amount:,.0f} {currency} — {type_name}".replace(",", " ")
    if desc:
        line += f" ({desc})"
    line += f" • {date_str}"
    
    return line


# ==============================================================
# Keyboards
# ==============================================================

def kb_wallet_card(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("admin:wallet:deposit", lang), callback_data=f"wallet:dep:{user_id}"),
            InlineKeyboardButton(text=t("admin:wallet:withdraw", lang), callback_data=f"wallet:wdr:{user_id}"),
        ],
        [InlineKeyboardButton(text=t("admin:wallet:history", lang), callback_data=f"wallet:hist:{user_id}")],
        [InlineKeyboardButton(text=t("admin:wallet:to_card", lang), callback_data=f"client:view:{user_id}")]
    ])


def kb_cancel_wallet(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"wallet:card:{user_id}")]
    ])


def kb_skip(user_id: int, op: str, lang: str) -> InlineKeyboardMarkup:
    """Кнопка пропустить комментарий."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"wallet:{op}_skip:{user_id}")],
        [InlineKeyboardButton(text=t("common:cancel", lang), callback_data=f"wallet:card:{user_id}")]
    ])


def kb_history(txs: list, user_id: int, page: int, total: int, lang: str) -> InlineKeyboardMarkup:
    rows = []
    
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    nav = build_nav_row(page, total_pages, f"wallet:hist:{user_id}:{{p}}", "wallet:noop", lang)
    if nav:
        rows.append(nav)
    
    rows.append([InlineKeyboardButton(text=t("admin:wallet:to_card", lang), callback_data=f"client:view:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==============================================================
# Setup
# ==============================================================

def setup(menu_controller, api):
    router = Router(name="clients_wallets")
    mc = menu_controller

    # ----------------------------------------------------------
    # show_wallet - экспортируется
    # ----------------------------------------------------------
    
    async def show_wallet(callback: CallbackQuery, state: FSMContext, user_id: int):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        user = await api.get_user(user_id)
        wallet = await api.get_wallet(user_id) or {}
        
        if not user:
            await callback.answer("Не найден", show_alert=True)
            return
        
        await state.update_data(wallet_user_id=user_id)
        
        name = _format_name(user)
        balance = wallet.get("balance", 0)
        
        lines = [
            t("admin:wallet:title", lang, name),
            "",
            t("admin:wallet:balance", lang, _format_balance(balance, lang)),
        ]
        
        await mc.edit_inline(callback.message, "\n".join(lines), kb_wallet_card(user_id, lang))
        await callback.answer()
    
    router.show_wallet = show_wallet

    # ----------------------------------------------------------
    # Callback: карточка кошелька
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("wallet:card:"))
    async def wallet_card(callback: CallbackQuery, state: FSMContext):
        user_id = int(callback.data.split(":")[2])
        await state.set_state(None)
        await show_wallet(callback, state, user_id)

    @router.callback_query(F.data == "wallet:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    # ----------------------------------------------------------
    # Пополнение
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("wallet:dep:"))
    async def start_deposit(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        
        await state.set_state(WalletOp.deposit_amount)
        await state.update_data(wallet_user_id=user_id)
        
        text = t("admin:wallet:enter_amount", lang)
        await mc.edit_inline_input(callback.message, text, kb_cancel_wallet(user_id, lang))
        await callback.answer()

    @router.message(WalletOp.deposit_amount)
    async def deposit_amount(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        
        try:
            await message.delete()
        except Exception:
            pass
        
        amount = parse_amount(message.text)
        if not amount:
            data = await state.get_data()
            user_id = data.get("wallet_user_id")
            err = await message.answer(t("admin:wallet:error_amount", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return
        
        await state.update_data(deposit_amount=amount)
        await state.set_state(WalletOp.deposit_comment)
        
        data = await state.get_data()
        user_id = data.get("wallet_user_id")
        
        text = t("admin:wallet:enter_comment", lang)
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb_skip(user_id, "dep", lang))

    @router.message(WalletOp.deposit_comment)
    async def deposit_comment(message: Message, state: FSMContext):
        comment = message.text.strip()
        if comment.lower() in ("/skip", "skip", "-"):
            comment = None
        
        try:
            await message.delete()
        except Exception:
            pass
        
        await _execute_deposit(message.bot, message.chat.id, state, comment)

    @router.callback_query(F.data.startswith("wallet:dep_skip:"))
    async def deposit_skip_comment(callback: CallbackQuery, state: FSMContext):
        await _execute_deposit(callback.bot, callback.message.chat.id, state, None)
        await callback.answer()

    async def _execute_deposit(bot, chat_id: int, state: FSMContext, comment: str | None):
        data = await state.get_data()
        user_id = data.get("wallet_user_id")
        amount = data.get("deposit_amount")
        lang = user_lang.get(chat_id, DEFAULT_LANG)
        
        result = await api.wallet_deposit(user_id, amount, description=comment)
        
        await state.set_state(None)
        
        if result:
            new_balance = result.get("new_balance", 0)
            lines = [
                t("admin:wallet:success", lang),
                t("admin:wallet:new_balance", lang, _format_balance(new_balance, lang)),
            ]
            await mc.send_inline_in_flow(bot, chat_id, "\n".join(lines), kb_wallet_card(user_id, lang))
        else:
            await mc.send_inline_in_flow(bot, chat_id, "❌ Ошибка", kb_wallet_card(user_id, lang))

    # ----------------------------------------------------------
    # Списание
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("wallet:wdr:"))
    async def start_withdraw(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        user_id = int(callback.data.split(":")[2])
        
        await state.set_state(WalletOp.withdraw_amount)
        await state.update_data(wallet_user_id=user_id)
        
        wallet = await api.get_wallet(user_id) or {}
        balance = wallet.get("balance", 0)
        
        text = f"{t('admin:wallet:enter_amount', lang)}\n{t('admin:wallet:balance', lang, _format_balance(balance, lang))}"
        await mc.edit_inline_input(callback.message, text, kb_cancel_wallet(user_id, lang))
        await callback.answer()

    @router.message(WalletOp.withdraw_amount)
    async def withdraw_amount(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        
        try:
            await message.delete()
        except Exception:
            pass
        
        amount = parse_amount(message.text)
        if not amount:
            err = await message.answer(t("admin:wallet:error_amount", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return
        
        data = await state.get_data()
        user_id = data.get("wallet_user_id")
        
        wallet = await api.get_wallet(user_id) or {}
        balance = wallet.get("balance", 0)
        
        if amount > balance:
            err = await message.answer(t("admin:wallet:error_balance", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return
        
        await state.update_data(withdraw_amount=amount)
        await state.set_state(WalletOp.withdraw_comment)
        
        text = t("admin:wallet:enter_comment", lang)
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb_skip(user_id, "wdr", lang))

    @router.message(WalletOp.withdraw_comment)
    async def withdraw_comment(message: Message, state: FSMContext):
        comment = message.text.strip()
        if comment.lower() in ("/skip", "skip", "-"):
            comment = None
        
        try:
            await message.delete()
        except Exception:
            pass
        
        await _execute_withdraw(message.bot, message.chat.id, state, comment)

    @router.callback_query(F.data.startswith("wallet:wdr_skip:"))
    async def withdraw_skip_comment(callback: CallbackQuery, state: FSMContext):
        await _execute_withdraw(callback.bot, callback.message.chat.id, state, None)
        await callback.answer()

    async def _execute_withdraw(bot, chat_id: int, state: FSMContext, comment: str | None):
        data = await state.get_data()
        user_id = data.get("wallet_user_id")
        amount = data.get("withdraw_amount")
        lang = user_lang.get(chat_id, DEFAULT_LANG)
        
        result = await api.wallet_withdraw(user_id, amount, description=comment)
        
        await state.set_state(None)
        
        if result:
            new_balance = result.get("new_balance", 0)
            lines = [
                t("admin:wallet:success", lang),
                t("admin:wallet:new_balance", lang, _format_balance(new_balance, lang)),
            ]
            await mc.send_inline_in_flow(bot, chat_id, "\n".join(lines), kb_wallet_card(user_id, lang))
        else:
            await mc.send_inline_in_flow(bot, chat_id, "❌ Ошибка (недостаточно средств?)", kb_wallet_card(user_id, lang))

    # ----------------------------------------------------------
    # История
    # ----------------------------------------------------------
    
    @router.callback_query(F.data.startswith("wallet:hist:"))
    async def show_history(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        parts = callback.data.split(":")
        user_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        
        txs = await api.get_wallet_transactions(user_id)
        total = len(txs)
        
        if not txs:
            text = t("admin:wallet:history_empty", lang)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("admin:wallet:to_card", lang), callback_data=f"client:view:{user_id}")]
            ])
            await mc.edit_inline(callback.message, text, kb)
            await callback.answer()
            return
        
        start = page * PAGE_SIZE
        page_txs = txs[start:start + PAGE_SIZE]
        
        lines = [t("admin:wallet:history_title", lang), ""]
        for tx in page_txs:
            lines.append(_format_tx(tx, lang))
        
        await mc.edit_inline(callback.message, "\n".join(lines), kb_history(page_txs, user_id, page, total, lang))
        await callback.answer()

    return router

