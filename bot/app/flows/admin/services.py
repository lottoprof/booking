"""
bot/app/flows/admin/services.py
FSM создания услуги + список / просмотр / удаление.
EDIT вынесен в services_edit.py (делегирование).

Ответственность файла:
- LIST (inline)
- VIEW
- DELETE
- CREATE (FSM, Redis)
- делегирование EDIT
- Escape hatch для CREATE FSM
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, t_all, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.keyboards.admin import admin_services
import math

# EDIT entry point
from .services_edit import start_service_edit, setup as setup_edit

logger = logging.getLogger(__name__)
PAGE_SIZE = 5


# ==============================================================
# Inline keyboards
# ==============================================================

def _format_service_item(svc: dict, lang: str) -> str:
    """
    Форматирует услугу для отображения в списке.
    
    Формат: 🛎  Название | 60+10 мин | 2500₽
    или:    🛎  Название | 60 мин | 2500₽ (без перерыва)
    """
    name = svc.get("name", "?")
    duration = svc.get("duration_min", 0)
    break_min = svc.get("break_min", 0)
    price = svc.get("price", 0)

    if break_min > 0:
        time_str = f"{duration}+{break_min}"
    else:
        time_str = str(duration)

    if price == int(price):
        price_str = f"{int(price)}{t('common:currency', lang)}"
    else:
        price_str = f"{price:.0f}{t('common:currency', lang)}"

    return f"{t('admin:services:item_icon', lang)} {name} | {time_str}{t('common:min', lang)} | {price_str}"


def services_list_inline(
    services: list[dict],
    page: int,
    lang: str,
    per_page: int = 5
) -> InlineKeyboardMarkup:
    """Список услуг с пагинацией."""
    from aiogram.types import InlineKeyboardButton
    
    total = len(services)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_items = services[start:end]

    buttons = []

    for svc in page_items:
        buttons.append([
            InlineKeyboardButton(
                text=_format_service_item(svc, lang),
                callback_data=f"svc:view:{svc['id']}"
            )
        ])

    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text=t("common:prev", lang),
                callback_data=f"svc:page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="svc:noop"
            ))

        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="svc:noop"
        ))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text=t("common:next", lang),
                callback_data=f"svc:page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="svc:noop"
            ))

        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="svc:back"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def service_view_inline(service: dict, lang: str) -> InlineKeyboardMarkup:
    """Карточка просмотра услуги."""
    from aiogram.types import InlineKeyboardButton
    
    svc_id = service["id"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:service:edit", lang),
                callback_data=f"svc:edit:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:service:delete", lang),
                callback_data=f"svc:delete:{svc_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data="svc:list:0"
            )
        ]
    ])


def service_delete_confirm_inline(svc_id: int, lang: str) -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    from aiogram.types import InlineKeyboardButton
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:yes", lang),
                callback_data=f"svc:delete_confirm:{svc_id}"
            ),
            InlineKeyboardButton(
                text=t("common:no", lang),
                callback_data=f"svc:view:{svc_id}"
            )
        ]
    ])


def service_cancel_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при создании."""
    from aiogram.types import InlineKeyboardButton
    
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="svc_create:cancel"
        )
    ]])


def service_skip_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка пропустить + отмена."""
    from aiogram.types import InlineKeyboardButton
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:skip", lang),
                callback_data="svc_create:skip"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:cancel", lang),
                callback_data="svc_create:cancel"
            )
        ]
    ])


def get_color_codes(lang: str) -> list[str]:
    """Получить список кодов цветов из i18n."""
    colors_str = t("colors:list", lang)
    return [c.strip() for c in colors_str.split(",") if c.strip()]


def color_picker_inline(lang: str) -> InlineKeyboardMarkup:
    """Выбор цвета услуги (создание)."""
    from aiogram.types import InlineKeyboardButton
    
    buttons = []
    row = []

    for color_code in get_color_codes(lang):
        emoji = t(f"color:{color_code}", lang)
        row.append(InlineKeyboardButton(
            text=emoji,
            callback_data=f"svc_color:{color_code}"
        ))

        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text=t("admin:service:color_none", lang),
            callback_data="svc_color:none"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="svc_create:cancel"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==============================================================
# FSM: CREATE
# ==============================================================

class ServiceCreate(StatesGroup):
    name = State()
    description = State()
    duration = State()
    break_min = State()
    price = State()
    color = State()


# ==============================================================
# Helpers (CREATE / VIEW)
# ==============================================================

def build_progress_text(data: dict, lang: str, prompt_key: str) -> str:
    """Текст с прогрессом создания услуги."""
    lines = [t("admin:service:create_title", lang), ""]

    if data.get("name"):
        lines.append(f"🛎 {data['name']}")
    if data.get("description"):
        lines.append(f"📝 {data['description']}")
    if data.get("duration"):
        lines.append(f"⏱ {data['duration']} мин")
    if data.get("break_min") is not None and data["break_min"] > 0:
        lines.append(f"☕ +{data['break_min']} мин перерыв")
    if data.get("price") is not None:
        lines.append(f"💰 {data['price']}")

    lines.append("")
    lines.append(t(prompt_key, lang))
    return "\n".join(lines)


def build_service_view_text(svc: dict, lang: str) -> str:
    """Карточка услуги."""
    lines = [f"🛎 {svc['name']}", ""]

    if svc.get("description"):
        lines.append(f"📝 {svc['description']}")
        lines.append("")

    duration = svc.get("duration_min", 0)
    break_min = svc.get("break_min", 0)

    if break_min > 0:
        lines.append(
            t("admin:service:info_break", lang)
            % (duration, break_min, svc.get("price", 0))
        )
    else:
        lines.append(
            t("admin:service:info", lang)
            % (duration, svc.get("price", 0))
        )

    if svc.get("color_code"):
        lines.append(f"🎨 {svc['color_code']}")

    return "\n".join(lines)


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    router = Router(name="services")
    logger.info("=== services.setup() called ===")

    # ==========================================================
    # ESCAPE HATCH: Reply "Back" во время CREATE FSM
    # ==========================================================

    @router.message(F.text.in_(t_all("admin:services:back")), ServiceCreate.name)
    @router.message(F.text.in_(t_all("admin:services:back")), ServiceCreate.description)
    @router.message(F.text.in_(t_all("admin:services:back")), ServiceCreate.duration)
    @router.message(F.text.in_(t_all("admin:services:back")), ServiceCreate.break_min)
    @router.message(F.text.in_(t_all("admin:services:back")), ServiceCreate.price)
    @router.message(F.text.in_(t_all("admin:services:back")), ServiceCreate.color)
    async def escape_create_fsm(message: Message, state: FSMContext):
        """
        Escape hatch: Reply-кнопка "Назад" во время FSM создания.
        Очищает состояние и возвращает в меню Services.
        """
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.back_to_reply(
            message,
            admin_services(lang),
            title=t("admin:services:title", lang),
            menu_context="services",
        )

    # ==========================================================
    # LIST
    # ==========================================================

    async def show_list(message: Message, page: int = 0):
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)

        services = await api.get_services()
        total = len(services)

        if total == 0:
            text = f"🛎 {t('admin:services:empty', lang)}"
        else:
            text = t("admin:services:list_title", lang) % total

        kb = services_list_inline(services, page, lang)
        await mc.show_inline_readonly(message, text, kb)

    router.show_list = show_list

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

    @router.callback_query(F.data == "svc:back")
    async def list_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.back_to_reply(
            callback.message,
            admin_services(lang),
            title=t("admin:services:title", lang),
            menu_context="services", 
        )
        await callback.answer()

    # ==========================================================
    # VIEW
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:view:"))
    async def view_service(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

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
    # EDIT (delegation only)
    # ==========================================================

    @router.callback_query(F.data.startswith("svc:edit:"))
    async def edit_service(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        await start_service_edit(
            mc=mc,
            callback=callback,
            state=state,
            svc_id=svc_id,
        )

    # ==========================================================
    # DELETE
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

        ok = await api.delete_service(svc_id)
        if not ok:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        await callback.answer(t("admin:service:deleted", lang))

        services = await api.get_services()
        total = len(services)

        if total == 0:
            text = f"🛎 {t('admin:services:empty', lang)}"
        else:
            text = t("admin:services:list_title", lang) % total

        kb = services_list_inline(services, 0, lang)
        await mc.edit_inline(callback.message, text, kb)

    # ==========================================================
    # CREATE
    # ==========================================================

    async def start_create(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        await state.set_state(ServiceCreate.name)
        await state.update_data(lang=lang)

        text = f"{t('admin:service:create_title', lang)}\n\n{t('admin:service:enter_name', lang)}"
        await mc.show_inline_input(message, text, service_cancel_inline(lang))

    router.start_create = start_create

    # ---- name
    @router.message(ServiceCreate.name)
    async def create_name(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()

        if len(name) < 2:
            await mc.show_inline_input(message, t("admin:service:error_name", lang), service_cancel_inline(lang))
            return

        await state.update_data(name=name)
        await state.set_state(ServiceCreate.description)

        data = await state.get_data()
        await mc.show_inline_input(
            message,
            build_progress_text(data, lang, "admin:service:enter_description"),
            service_skip_inline(lang),
        )

    # ---- description
    @router.callback_query(F.data == "svc_create:skip", ServiceCreate.description)
    async def skip_description(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.update_data(description=None)
        await state.set_state(ServiceCreate.duration)

        data = await state.get_data()
        await callback.message.edit_text(
            build_progress_text(data, lang, "admin:service:enter_duration"),
            reply_markup=service_cancel_inline(lang),
        )
        await callback.answer()

    @router.message(ServiceCreate.description)
    async def create_description(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.update_data(description=message.text.strip() or None)
        await state.set_state(ServiceCreate.duration)

        data = await state.get_data()
        await mc.show_inline_input(
            message,
            build_progress_text(data, lang, "admin:service:enter_duration"),
            service_cancel_inline(lang),
        )

    # ---- duration
    @router.message(ServiceCreate.duration)
    async def create_duration(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        try:
            duration = int(message.text.strip())
            if duration <= 0:
                raise ValueError()
        except ValueError:
            await mc.show_inline_input(message, t("admin:service:error_duration", lang), service_cancel_inline(lang))
            return

        await state.update_data(duration=duration)
        await state.set_state(ServiceCreate.break_min)

        data = await state.get_data()
        await mc.show_inline_input(
            message,
            build_progress_text(data, lang, "admin:service:enter_break"),
            service_skip_inline(lang),
        )

    # ---- break
    @router.callback_query(F.data == "svc_create:skip", ServiceCreate.break_min)
    async def skip_break(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.update_data(break_min=0)
        await state.set_state(ServiceCreate.price)

        data = await state.get_data()
        await callback.message.edit_text(
            build_progress_text(data, lang, "admin:service:enter_price"),
            reply_markup=service_cancel_inline(lang),
        )
        await callback.answer()

    @router.message(ServiceCreate.break_min)
    async def create_break(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        try:
            break_min = int(message.text.strip())
            if break_min < 0:
                raise ValueError()
        except ValueError:
            await mc.show_inline_input(message, t("admin:service:error_break", lang), service_skip_inline(lang))
            return

        await state.update_data(break_min=break_min)
        await state.set_state(ServiceCreate.price)

        data = await state.get_data()
        await mc.show_inline_input(
            message,
            build_progress_text(data, lang, "admin:service:enter_price"),
            service_cancel_inline(lang),
        )

    # ---- price
    @router.message(ServiceCreate.price)
    async def create_price(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        try:
            price = float(message.text.strip().replace(",", "."))
            if price < 0:
                raise ValueError()
        except ValueError:
            await mc.show_inline_input(message, t("admin:service:error_price", lang), service_cancel_inline(lang))
            return

        await state.update_data(price=price)
        await state.set_state(ServiceCreate.color)

        data = await state.get_data()
        await mc.show_inline_input(
            message,
            build_progress_text(data, lang, "admin:service:choose_color"),
            color_picker_inline(lang),
        )

    # ---- color / save
    @router.callback_query(F.data.startswith("svc_color:"), ServiceCreate.color)
    async def create_color(callback: CallbackQuery, state: FSMContext):
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
            title=t("admin:services:title", lang),
            menu_context="services",
        )

    # ---- cancel create
    @router.callback_query(F.data == "svc_create:cancel")
    async def cancel_create(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await callback.answer()
        await mc.back_to_reply(
            callback.message,
            admin_services(lang),
            title=t("admin:services:title", lang),
            menu_context="services", 
        )

    # подключаем EDIT router
    router.include_router(setup_edit(mc, get_user_role))

    logger.info("=== services router configured ===")
    return router
