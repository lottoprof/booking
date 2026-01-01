"""
bot/app/flows/admin/services_edit.py

EDIT-FSM for Services (admin).
Вынесено из services.py без изменения бизнес-логики.

Правила:
- FSM в Redis (через общий aiogram storage)
- PATCH только diff (changes)
- Inline-only
- Не управляет Reply/menu_context (это делает services.py/admin_reply.py)
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.keyboards.admin import (
    service_view_inline,
    service_cancel_inline,
    color_picker_inline,
)

logger = logging.getLogger(__name__)


# ==============================================================
# FSM States (EDIT)
# ==============================================================

class ServiceEdit(StatesGroup):
    """FSM для редактирования услуги."""
    name = State()
    description = State()
    duration = State()
    break_min = State()
    price = State()
    color = State()


# ==============================================================
# Inline keyboards for EDIT
# ==============================================================

def service_edit_inline(svc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Экран редактирования услуги."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:service:edit_name", lang),
                callback_data=f"svc:edit_name:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:service:edit_desc", lang),
                callback_data=f"svc:edit_desc:{svc_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("admin:service:edit_duration", lang),
                callback_data=f"svc:edit_duration:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:service:edit_break", lang),
                callback_data=f"svc:edit_break:{svc_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("admin:service:edit_price", lang),
                callback_data=f"svc:edit_price:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:service:edit_color", lang),
                callback_data=f"svc:edit_color:{svc_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("common:save", lang),
                callback_data=f"svc:save:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data=f"svc:view:{svc_id}"
            ),
        ],
    ])


def service_edit_cancel_inline(svc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при редактировании поля."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"svc:edit:{svc_id}"  # попадёт в делегат services.py → start_service_edit()
        )
    ]])


# Коды цветов берутся из i18n
def get_color_codes(lang: str) -> list[str]:
    """Получить список кодов цветов из i18n."""
    colors_str = t("colors:list", lang)
    return [c.strip() for c in colors_str.split(",") if c.strip()]


def color_picker_edit_inline(svc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Выбор цвета при редактировании."""
    buttons = []
    row = []

    for color_code in get_color_codes(lang):
        emoji = t(f"color:{color_code}", lang)
        row.append(InlineKeyboardButton(
            text=emoji,
            callback_data=f"svc:color:{svc_id}:{color_code}"
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
            callback_data=f"svc:color:{svc_id}:none"
        )
    ])

    # Отмена
    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"svc:edit:{svc_id}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==============================================================
# Helpers: texts
# ==============================================================

def build_service_view_text(svc: dict, lang: str) -> str:
    """Текст карточки услуги (дублируем минимально, чтобы EDIT был самодостаточным)."""
    lines = [f"🛎 {svc['name']}", ""]

    if svc.get("description"):
        lines.append(f"📝 {svc['description']}")
        lines.append("")

    duration = svc.get("duration_min", 0)
    break_min = svc.get("break_min", 0)

    if break_min > 0:
        lines.append(t("admin:service:info_break", lang) % (duration, break_min, svc.get("price", 0)))
    else:
        lines.append(t("admin:service:info", lang) % (duration, svc.get("price", 0)))

    if svc.get("color_code"):
        lines.append(f"🎨 {svc['color_code']}")

    return "\n".join(lines)


def build_service_edit_text(svc: dict, changes: dict, lang: str) -> str:
    """
    Текст экрана редактирования.
    Показывает текущие значения + изменения из changes.
    """
    name = changes.get("name", svc.get("name", ""))
    description = changes.get("description", svc.get("description"))
    duration = changes.get("duration_min", svc.get("duration_min", 0))
    break_min = changes.get("break_min", svc.get("break_min", 0))
    price = changes.get("price", svc.get("price", 0))
    color_code = changes.get("color_code", svc.get("color_code"))

    lines = [t("admin:service:edit_title", lang), ""]
    lines.append(f"🛎 {name}")

    if description:
        lines.append(f"📝 {description}")

    if break_min > 0:
        lines.append(f"⏱ {duration} мин (+{break_min} перерыв)")
    else:
        lines.append(f"⏱ {duration} мин")

    if isinstance(price, (int, float)) and price == int(price):
        lines.append(f"💰 {int(price)}₽")
    else:
        lines.append(f"💰 {price}₽")

    if color_code:
        lines.append(f"🎨 {color_code}")

    if changes:
        lines.append("")
        changed_names = _get_changed_field_names(changes, lang)
        if changed_names:
            lines.append("✏️ " + ", ".join(changed_names))

    return "\n".join(lines)


def _get_changed_field_names(changes: dict, lang: str) -> list[str]:
    """Возвращает читаемые имена изменённых полей."""
    field_map = {
        "name": "admin:service:edit_name",
        "description": "admin:service:edit_desc",
        "duration_min": "admin:service:edit_duration",
        "break_min": "admin:service:edit_break",
        "price": "admin:service:edit_price",
        "color_code": "admin:service:edit_color",
    }

    names = []
    for field, key in field_map.items():
        if field in changes:
            name = t(key, lang)
            for emoji in ["✏️ ", "📝 ", "⏱ ", "☕ ", "💰 ", "🎨 "]:
                name = name.replace(emoji, "")
            names.append(name)

    return names


# ==============================================================
# Entry point (called from services.py delegate)
# ==============================================================

async def start_service_edit(*, mc, callback: CallbackQuery, state: FSMContext, svc_id: int) -> None:
    """
    Entry point редактирования услуги.

    ВАЖНО:
    - обработчик svc:edit:{id} находится в services.py и просто делегирует сюда.
    - здесь только инициализация + показ edit-экрана.
    """
    lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

    service = await api.get_service(svc_id)
    if not service:
        await callback.answer(t("common:error", lang), show_alert=True)
        return

    data = await state.get_data()

    # Если новый вход или другой svc_id — инициализируем заново
    if data.get("edit_svc_id") != svc_id:
        await state.update_data(
            edit_svc_id=svc_id,
            original=service,
            changes={}
        )
        data = await state.get_data()

    changes = data.get("changes", {})
    text = build_service_edit_text(service, changes, lang)
    kb = service_edit_inline(svc_id, lang)

    # Активируем IME для режима редактирования (удалит reply-якорь)
    await mc.edit_inline_input(callback.message, text, kb)
    await callback.answer()


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    """
    Setup router with dependencies.
    Возвращает Router с EDIT handlers.
    """

    router = Router(name="services_edit")
    logger.info("=== services_edit.setup() called ===")

    # ==========================================================
    # EDIT: name
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit_name:"))
    async def edit_name_start(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(ServiceEdit.name)

        text = t("admin:service:enter_name", lang)
        kb = service_edit_cancel_inline(svc_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(ServiceEdit.name)
    async def edit_name_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()

        if len(name) < 2:
            err_msg = await message.answer(t("admin:service:error_name", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

        data = await state.get_data()
        svc_id = data.get("edit_svc_id")
        changes = data.get("changes", {})
        changes["name"] = name

        await state.update_data(changes=changes)
        await state.set_state(None)

        service = data.get("original", {})
        text = build_service_edit_text(service, changes, lang)
        kb = service_edit_inline(svc_id, lang)

        try:
            await message.delete()
        except Exception:
            pass

        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: description
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit_desc:"))
    async def edit_desc_start(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(ServiceEdit.description)

        text = t("admin:service:enter_description", lang)
        kb = service_edit_cancel_inline(svc_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(ServiceEdit.description)
    async def edit_desc_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        description = message.text.strip()

        data = await state.get_data()
        svc_id = data.get("edit_svc_id")
        changes = data.get("changes", {})
        changes["description"] = description if description else None

        await state.update_data(changes=changes)
        await state.set_state(None)

        service = data.get("original", {})
        text = build_service_edit_text(service, changes, lang)
        kb = service_edit_inline(svc_id, lang)

        try:
            await message.delete()
        except Exception:
            pass

        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: duration
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit_duration:"))
    async def edit_duration_start(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(ServiceEdit.duration)

        text = t("admin:service:enter_duration", lang)
        kb = service_edit_cancel_inline(svc_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(ServiceEdit.duration)
    async def edit_duration_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        try:
            duration = int(message.text.strip())
            if duration <= 0:
                raise ValueError()
        except ValueError:
            err_msg = await message.answer(t("admin:service:error_duration", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

        data = await state.get_data()
        svc_id = data.get("edit_svc_id")
        changes = data.get("changes", {})
        changes["duration_min"] = duration

        await state.update_data(changes=changes)
        await state.set_state(None)

        service = data.get("original", {})
        text = build_service_edit_text(service, changes, lang)
        kb = service_edit_inline(svc_id, lang)

        try:
            await message.delete()
        except Exception:
            pass

        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: break_min
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit_break:"))
    async def edit_break_start(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(ServiceEdit.break_min)

        text = t("admin:service:enter_break", lang)
        kb = service_edit_cancel_inline(svc_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(ServiceEdit.break_min)
    async def edit_break_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        try:
            break_min = int(message.text.strip())
            if break_min < 0:
                raise ValueError()
        except ValueError:
            err_msg = await message.answer(t("admin:service:error_break", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

        data = await state.get_data()
        svc_id = data.get("edit_svc_id")
        changes = data.get("changes", {})
        changes["break_min"] = break_min

        await state.update_data(changes=changes)
        await state.set_state(None)

        service = data.get("original", {})
        text = build_service_edit_text(service, changes, lang)
        kb = service_edit_inline(svc_id, lang)

        try:
            await message.delete()
        except Exception:
            pass

        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: price
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit_price:"))
    async def edit_price_start(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(ServiceEdit.price)

        text = t("admin:service:enter_price", lang)
        kb = service_edit_cancel_inline(svc_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(ServiceEdit.price)
    async def edit_price_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        try:
            price_text = message.text.strip().replace(",", ".")
            price = float(price_text)
            if price < 0:
                raise ValueError()
        except ValueError:
            err_msg = await message.answer(t("admin:service:error_price", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

        data = await state.get_data()
        svc_id = data.get("edit_svc_id")
        changes = data.get("changes", {})
        changes["price"] = price

        await state.update_data(changes=changes)
        await state.set_state(None)

        service = data.get("original", {})
        text = build_service_edit_text(service, changes, lang)
        kb = service_edit_inline(svc_id, lang)

        try:
            await message.delete()
        except Exception:
            pass

        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ==========================================================
    # EDIT: color
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit_color:"))
    async def edit_color_start(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(ServiceEdit.color)

        text = t("admin:service:choose_color", lang)
        kb = color_picker_edit_inline(svc_id, lang)

        # Для выбора цвета не нужен IME — используем edit_inline
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("svc:color:"), ServiceEdit.color)
    async def edit_color_process(callback: CallbackQuery, state: FSMContext):
        parts = callback.data.split(":")
        svc_id = int(parts[2])
        color_value = parts[3]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        color_code = None if color_value == "none" else color_value

        data = await state.get_data()
        changes = data.get("changes", {})
        changes["color_code"] = color_code

        await state.update_data(changes=changes)
        await state.set_state(None)

        service = data.get("original", {})
        text = build_service_edit_text(service, changes, lang)
        kb = service_edit_inline(svc_id, lang)

        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ==========================================================
    # SAVE: применить все изменения
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:save:"))
    async def save_service(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        changes = data.get("changes", {})

        if not changes:
            await callback.answer(t("admin:service:no_changes", lang))
            return

        result = await api.update_service(svc_id, **changes)
        if not result:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        await state.clear()
        await callback.answer(t("admin:service:saved", lang))

        # Показать обновлённую карточку
        service = await api.get_service(svc_id)
        if service:
            text = build_service_view_text(service, lang)
            kb = service_view_inline(service, lang)
            await mc.edit_inline(callback.message, text, kb)

    logger.info("=== services_edit router configured ===")
    return router

