"""
bot/app/flows/admin/services.py

FSM создания + редактирования услуги + Inline CRUD handlers.
"""

import logging
import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.keyboards.admin import (
    admin_services,
    services_list_inline,
    service_view_inline,
    service_delete_confirm_inline,
    service_cancel_inline,
    service_skip_inline,
    color_picker_inline,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


# ==============================================================
# FSM States
# ==============================================================

class ServiceCreate(StatesGroup):
    name = State()
    description = State()
    duration = State()
    break_min = State()
    price = State()
    color = State()


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
            callback_data=f"svc:edit:{svc_id}"
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
        # Emoji из i18n по коду цвета
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
# Helper: build texts
# ==============================================================

def build_progress_text(data: dict, lang: str, prompt_key: str) -> str:
    """Строит текст с прогрессом заполнения (создание)."""
    lines = [t("admin:service:create_title", lang), ""]
    
    if data.get("name"):
        lines.append(f"🛎 {data['name']}")
    if data.get("description"):
        lines.append(f"📝 {data['description']}")
    if data.get("duration"):
        lines.append(f"⏱ {data['duration']} мин")
    if data.get("break_min") is not None:
        if data["break_min"] > 0:
            lines.append(f"☕ +{data['break_min']} мин перерыв")
    if data.get("price") is not None:
        lines.append(f"💰 {data['price']}")
    
    lines.append("")
    lines.append(t(prompt_key, lang))
    
    return "\n".join(lines)


def build_service_view_text(svc: dict, lang: str) -> str:
    """Текст карточки услуги."""
    lines = [f"🛎 {svc['name']}", ""]
    
    if svc.get("description"):
        lines.append(f"📝 {svc['description']}")
        lines.append("")
    
    # Время
    duration = svc.get("duration_min", 0)
    break_min = svc.get("break_min", 0)
    
    if break_min > 0:
        lines.append(t("admin:service:info_break", lang) % (duration, break_min, svc.get("price", 0)))
    else:
        lines.append(t("admin:service:info", lang) % (duration, svc.get("price", 0)))
    
    # Цвет
    if svc.get("color_code"):
        lines.append(f"🎨 {svc['color_code']}")
    
    return "\n".join(lines)


def build_service_edit_text(svc: dict, changes: dict, lang: str) -> str:
    """
    Текст экрана редактирования.
    Показывает текущие значения + изменения из changes.
    """
    # Применяем изменения для отображения
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
    
    # Время
    if break_min > 0:
        lines.append(f"⏱ {duration} мин (+{break_min} перерыв)")
    else:
        lines.append(f"⏱ {duration} мин")
    
    # Цена
    if price == int(price):
        lines.append(f"💰 {int(price)}₽")
    else:
        lines.append(f"💰 {price}₽")
    
    # Цвет
    if color_code:
        lines.append(f"🎨 {color_code}")
    
    # Показываем что изменено
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
            # Убираем emoji из названия
            name = t(key, lang)
            for emoji in ["✏️ ", "📝 ", "⏱ ", "☕ ", "💰 ", "🎨 "]:
                name = name.replace(emoji, "")
            names.append(name)
    
    return names


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    """Setup router with dependencies."""
    
    router = Router(name="services")
    logger.info("=== services.setup() called ===")

    # ==========================================================
    # LIST: показать список услуг
    # ==========================================================

    async def show_list(message: Message, page: int = 0):
        """Показать список услуг (вызывается из admin_reply)."""
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        services = await api.get_services()
        total = len(services)
        
        if total == 0:
            text = f"🛎 {t('admin:services:empty', lang)}"
        else:
            text = t("admin:services:list_title", lang) % total
        
        kb = services_list_inline(services, page, lang)
        
        # Type B1: readonly — Reply-якорь сохраняется, IME не появляется
        await mc.show_inline_readonly(message, text, kb)

    router.show_list = show_list

    # ==========================================================
    # LIST: pagination callback
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:page:"))
    async def list_page(callback: CallbackQuery):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        services = await api.get_services()
        total = len(services)
        
        if total == 0:
            text = f"🛎 {t('admin:services:empty', lang)}"
        else:
            text = t("admin:services:list_title", lang) % total
        
        kb = services_list_inline(services, page, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "svc:list:0")
    async def list_first_page(callback: CallbackQuery):
        """Вернуться к первой странице списка."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        services = await api.get_services()
        total = len(services)
        
        if total == 0:
            text = f"🛎 {t('admin:services:empty', lang)}"
        else:
            text = t("admin:services:list_title", lang) % total
        
        kb = services_list_inline(services, 0, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "svc:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    # ==========================================================
    # LIST: back to Reply menu
    # ==========================================================

    @router.callback_query(F.data == "svc:back")
    async def list_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.back_to_reply(
            callback.message,
            admin_services(lang),
            title=t("admin:services:title", lang)
        )
        await callback.answer()

    # ==========================================================
    # VIEW: карточка услуги
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:view:"))
    async def view_service(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        # Очищаем FSM при возврате на просмотр
        await state.clear()
        
        service = await api.get_service(svc_id)
        if not service:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        text = build_service_view_text(service, lang)
        kb = service_view_inline(service, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ==========================================================
    # DELETE: подтверждение
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:delete:"))
    async def delete_confirm(callback: CallbackQuery):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        service = await api.get_service(svc_id)
        if not service:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        text = t("admin:service:confirm_delete", lang) % service["name"]
        kb = service_delete_confirm_inline(svc_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("svc:delete_confirm:"))
    async def delete_execute(callback: CallbackQuery):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        success = await api.delete_service(svc_id)
        if success:
            await callback.answer(t("admin:service:deleted", lang))
        else:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        # Вернуться к списку
        services = await api.get_services()
        total = len(services)
        
        if total == 0:
            text = f"🛎 {t('admin:services:empty', lang)}"
        else:
            text = t("admin:services:list_title", lang) % total
        
        kb = services_list_inline(services, 0, lang)
        await mc.edit_inline(callback.message, text, kb)

    # ==========================================================
    # EDIT: показать экран редактирования
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit:"))
    async def edit_service(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        service = await api.get_service(svc_id)
        if not service:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        # Получаем текущие изменения из FSM (если есть)
        data = await state.get_data()
        
        # Если это новый вход в редактирование — инициализируем
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
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

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
        
        # edit_inline_input — удаляет Reply-якорь, активирует IME
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
            except:
                pass
            return
        
        data = await state.get_data()
        svc_id = data.get("edit_svc_id")
        changes = data.get("changes", {})
        changes["name"] = name
        
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        # Возвращаемся на экран редактирования
        service = data.get("original", {})
        text = build_service_edit_text(service, changes, lang)
        kb = service_edit_inline(svc_id, lang)
        
        try:
            await message.delete()
        except:
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
        except:
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
            except:
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
        except:
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
            except:
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
        except:
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
            except:
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
        except:
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
        
        # PATCH запрос
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

    # ==========================================================
    # START CREATE
    # ==========================================================
    
    async def start_create(message: Message, state: FSMContext):
        """Entry point — вызывается из admin_reply."""
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        logger.info(f"services.start_create called")
        
        await state.set_state(ServiceCreate.name)
        await state.update_data(lang=lang)
        
        text = f"{t('admin:service:create_title', lang)}\n\n{t('admin:service:enter_name', lang)}"
        
        # Type B2: input — Reply-якорь удаляется, IME активен для ввода
        await mc.show_inline_input(message, text, service_cancel_inline(lang))

    router.start_create = start_create

    # ==========================================================
    # Helper: send tracked inline
    # ==========================================================

    async def send_step(message: Message, text: str, kb: InlineKeyboardMarkup):
        """Отправить inline с трекингом для очистки."""
        chat_id = message.chat.id
        bot = message.bot
        
        try:
            await message.delete()
        except:
            pass
        
        return await mc.send_inline_in_flow(bot, chat_id, text, kb)

    # ==========================================================
    # NAME → DESCRIPTION (CREATE)
    # ==========================================================

    @router.message(ServiceCreate.name)
    async def process_name(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()
        
        if len(name) < 2:
            try:
                await message.delete()
            except:
                pass
            err_msg = await message.answer(t("admin:service:error_name", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            return
        
        await state.update_data(name=name)
        await state.set_state(ServiceCreate.description)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:service:enter_description")
        await send_step(message, text, service_skip_inline(lang))

    # ==========================================================
    # DESCRIPTION → DURATION (or skip) (CREATE)
    # ==========================================================

    @router.callback_query(F.data == "svc_create:skip", ServiceCreate.description)
    async def skip_description(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.update_data(description=None)
        await state.set_state(ServiceCreate.duration)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:service:enter_duration")
        
        await callback.message.edit_text(text, reply_markup=service_cancel_inline(lang))
        await callback.answer()

    @router.message(ServiceCreate.description)
    async def process_description(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        description = message.text.strip()
        
        await state.update_data(description=description if description else None)
        await state.set_state(ServiceCreate.duration)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:service:enter_duration")
        await send_step(message, text, service_cancel_inline(lang))

    # ==========================================================
    # DURATION → BREAK (CREATE)
    # ==========================================================

    @router.message(ServiceCreate.duration)
    async def process_duration(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        
        try:
            duration = int(message.text.strip())
            if duration <= 0:
                raise ValueError()
        except ValueError:
            try:
                await message.delete()
            except:
                pass
            err_msg = await message.answer(t("admin:service:error_duration", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            return
        
        await state.update_data(duration=duration)
        await state.set_state(ServiceCreate.break_min)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:service:enter_break")
        await send_step(message, text, service_skip_inline(lang))

    # ==========================================================
    # BREAK → PRICE (or skip = 0) (CREATE)
    # ==========================================================

    @router.callback_query(F.data == "svc_create:skip", ServiceCreate.break_min)
    async def skip_break(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.update_data(break_min=0)
        await state.set_state(ServiceCreate.price)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:service:enter_price")
        
        await callback.message.edit_text(text, reply_markup=service_cancel_inline(lang))
        await callback.answer()

    @router.message(ServiceCreate.break_min)
    async def process_break(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        
        try:
            break_min = int(message.text.strip())
            if break_min < 0:
                raise ValueError()
        except ValueError:
            try:
                await message.delete()
            except:
                pass
            err_msg = await message.answer(t("admin:service:error_break", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            return
        
        await state.update_data(break_min=break_min)
        await state.set_state(ServiceCreate.price)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:service:enter_price")
        await send_step(message, text, service_cancel_inline(lang))

    # ==========================================================
    # PRICE → COLOR (CREATE)
    # ==========================================================

    @router.message(ServiceCreate.price)
    async def process_price(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        
        try:
            price_text = message.text.strip().replace(",", ".")
            price = float(price_text)
            if price < 0:
                raise ValueError()
        except ValueError:
            try:
                await message.delete()
            except:
                pass
            err_msg = await message.answer(t("admin:service:error_price", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            return
        
        await state.update_data(price=price)
        await state.set_state(ServiceCreate.color)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:service:choose_color")
        await send_step(message, text, color_picker_inline(lang))

    # ==========================================================
    # COLOR → SAVE (CREATE)
    # ==========================================================

    @router.callback_query(F.data.startswith("svc_color:"), ServiceCreate.color)
    async def process_color(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        color_value = callback.data.split(":")[1]
        color_code = None if color_value == "none" else color_value
        
        data = await state.get_data()
        
        company = await api.get_company()
        if not company:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        service = await api.create_service(
            company_id=company["id"],
            name=data["name"],
            duration_min=data["duration"],
            price=data["price"],
            description=data.get("description"),
            break_min=data.get("break_min", 0),
            color_code=color_code,
        )
        
        if not service:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        await state.clear()
        await callback.answer(t("admin:service:created", lang) % data["name"])
        
        await mc.back_to_reply(
            callback.message,
            admin_services(lang),
            title=t("admin:services:title", lang)
        )

    # ==========================================================
    # CANCEL: any step (CREATE)
    # ==========================================================

    @router.callback_query(F.data == "svc_create:cancel")
    async def cancel_create(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.clear()
        await callback.answer()
        
        await mc.back_to_reply(
            callback.message,
            admin_services(lang),
            title=t("admin:services:title", lang)
        )

    logger.info("=== services router configured ===")
    return router

