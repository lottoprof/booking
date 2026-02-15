"""
bot/app/flows/admin/specialists.py

FSM создания специалиста + список / просмотр / удаление.
EDIT вынесен в specialists_edit.py (делегирование).

Ответственность файла:
- LIST (inline, пагинация)
- VIEW
- DELETE
- CREATE (FSM, Redis) — с обязательным выбором услуг
- делегирование EDIT
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
from bot.app.keyboards.admin import admin_specialists
from bot.app.keyboards.schedule import (
    schedule_day_edit_inline,
    schedule_days_inline,
)
from bot.app.utils.api import api
from bot.app.utils.pagination import build_nav_row
from bot.app.utils.schedule_helper import (
    default_schedule,  # noqa: F401
    format_day_value,
    format_schedule_compact,
    parse_time_input,
)
from bot.app.utils.state import user_lang

from .specialists_edit import setup as setup_edit

# EDIT entry point
from .specialists_edit import start_specialist_edit

logger = logging.getLogger(__name__)

# ==============================================================
# Config
# ==============================================================

PAGE_SIZE = 5
USER_SORT_BY = "name"  # "name" | "phone"


# ==============================================================
# FSM: CREATE
# ==============================================================

class SpecialistCreate(StatesGroup):
    user = State()           # выбор пользователя
    search_phone = State()   # поиск по телефону
    display_name = State()   # ввод отображаемого имени
    description = State()    # ввод описания
    services = State()       # выбор услуг
    schedule = State()       # редактирование графика
    schedule_day = State()   # редактирование одного дня


# ==============================================================
# Inline keyboards
# ==============================================================

def specialist_cancel_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при создании."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="spec_create:cancel"
        )
    ]])


def specialist_skip_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка пропустить + отмена."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:skip", lang),
                callback_data="spec_create:skip"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:cancel", lang),
                callback_data="spec_create:cancel"
            )
        ]
    ])


def users_select_inline(
    users: list[dict],
    existing_specialist_user_ids: set[int],
    lang: str,
    page: int = 0
) -> InlineKeyboardMarkup:
    """
    Выбор пользователя при создании специалиста.
    Фильтрует уже назначенных специалистами.
    """
    # Фильтруем пользователей которые уже специалисты
    available_users = [u for u in users if u["id"] not in existing_specialist_user_ids]
    
    # Сортировка
    if USER_SORT_BY == "phone":
        available_users.sort(key=lambda u: u.get("phone") or "")
    else:
        available_users.sort(key=lambda u: _get_user_full_name(u))
    
    total = len(available_users)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = available_users[start:end]
    
    buttons = []
    
    # Кнопка поиска
    buttons.append([
        InlineKeyboardButton(
            text=t("admin:specialist:search_phone", lang),
            callback_data="spec_create:search"
        )
    ])
    
    # Кнопки пользователей
    for user in page_items:
        name = _get_user_full_name(user)
        phone = user.get("phone") or ""
        
        if phone:
            text = t("admin:specialist:user_item", lang) % (name, phone)
        else:
            text = f"👤 {name}"
        
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"spec_create:user:{user['id']}"
            )
        ])
    
    # Пагинация
    nav = build_nav_row(page, total_pages, "spec_create:user_page:{p}", "spec_create:noop", lang)
    if nav:
        buttons.append(nav)
    
    # Отмена
    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="spec_create:cancel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def search_back_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка возврата к списку после поиска."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:specialist:search_back", lang),
                callback_data="spec_create:search_back"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:cancel", lang),
                callback_data="spec_create:cancel"
            )
        ]
    ])


def services_multiselect_inline(
    services: list[dict],
    selected_ids: set[int],
    lang: str,
    page: int = 0,
    prefix: str = "spec_create"
) -> InlineKeyboardMarkup:
    """
    Мульти-выбор услуг с пагинацией.
    ✅ — выбрана, ⬜ — не выбрана.
    """
    total = len(services)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = services[start:end]
    
    buttons = []
    
    for svc in page_items:
        is_selected = svc["id"] in selected_ids
        icon = "✅" if is_selected else "⬜"
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {svc['name']}",
                callback_data=f"{prefix}:svc_toggle:{svc['id']}"
            )
        ])
    
    # Пагинация
    nav = build_nav_row(page, total_pages, f"{prefix}:svc_page:{{p}}", f"{prefix}:noop", lang)
    if nav:
        buttons.append(nav)
    
    # Готово (с количеством)
    count = len(selected_ids)
    done_text = t("admin:specialist:services_selected", lang) % count
    
    buttons.append([
        InlineKeyboardButton(
            text=done_text,
            callback_data=f"{prefix}:svc_done" if count > 0 else f"{prefix}:noop"
        )
    ])
    
    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"{prefix}:cancel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def specialists_list_inline(
    specialists: list[dict],
    users_map: dict[int, dict],
    page: int,
    lang: str
) -> InlineKeyboardMarkup:
    """Список специалистов с пагинацией."""
    total = len(specialists)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = specialists[start:end]
    
    buttons = []
    
    for spec in page_items:
        # Берём display_name или имя из user
        name = spec.get("display_name")
        if not name:
            user = users_map.get(spec["user_id"], {})
            name = _get_user_full_name(user) if user else f"ID:{spec['user_id']}"
        
        text = t("admin:specialists:item", lang) % name
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"spec:view:{spec['id']}"
            )
        ])
    
    # Пагинация
    nav = build_nav_row(page, total_pages, "spec:page:{p}", "spec:noop", lang)
    if nav:
        buttons.append(nav)
    
    # Назад
    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="spec:back"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def specialist_view_inline(spec: dict, lang: str) -> InlineKeyboardMarkup:
    """Карточка просмотра специалиста."""
    spec_id = spec["id"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:specialist:edit", lang),
                callback_data=f"spec:edit:{spec_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:specialist:delete", lang),
                callback_data=f"spec:delete:{spec_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data="spec:list:0"
            )
        ]
    ])


def specialist_delete_confirm_inline(spec_id: int, lang: str) -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:yes", lang),
                callback_data=f"spec:delete_confirm:{spec_id}"
            ),
            InlineKeyboardButton(
                text=t("common:no", lang),
                callback_data=f"spec:view:{spec_id}"
            )
        ]
    ])


# ==============================================================
# Helpers
# ==============================================================

def _get_user_full_name(user: dict) -> str:
    """Получить полное имя пользователя."""
    first = user.get("first_name") or ""
    last = user.get("last_name") or ""
    return f"{first} {last}".strip() or "?"


def _specialist_default_schedule() -> dict:
    """Дефолтный график специалиста: Пн-Пт 10:00-19:00."""
    from bot.app.utils.schedule_helper import DAYS
    schedule = {}
    for day in DAYS:
        if day in ("sat", "sun"):
            schedule[day] = None
        else:
            schedule[day] = {"start": "10:00", "end": "19:00"}
    return schedule


def build_progress_text(data: dict, lang: str, prompt_key: str) -> str:
    """Текст с прогрессом создания специалиста."""
    lines = [t("admin:specialist:create_title", lang), ""]
    
    if data.get("user_name"):
        lines.append(f"👤 {data['user_name']}")
    if data.get("display_name"):
        lines.append(f"📛 {data['display_name']}")
    if data.get("description"):
        lines.append(f"📝 {data['description']}")
    
    selected_services = data.get("selected_services", [])
    if selected_services:
        lines.append(f"🛎 {t('admin:specialist:services_count', lang) % len(selected_services)}")
    
    lines.append("")
    lines.append(t(prompt_key, lang))
    return "\n".join(lines)


async def build_specialist_view_text(spec: dict, lang: str) -> str:
    """Текст карточки специалиста."""
    # Получаем user
    user = await api.get_user(spec["user_id"])
    
    # Имя
    name = spec.get("display_name")
    if not name and user:
        name = _get_user_full_name(user)
    name = name or "?"
    
    lines = [t("admin:specialist:view_title", lang) % name, ""]
    
    # Телефон
    if user and user.get("phone"):
        lines.append(t("admin:specialist:phone", lang) % user["phone"])
    else:
        lines.append(t("admin:specialist:no_phone", lang))
    
    # Описание
    if spec.get("description"):
        lines.append(f"📝 {spec['description']}")
    
    # График
    if spec.get("work_schedule"):
        try:
            schedule = json.loads(spec["work_schedule"]) if isinstance(spec["work_schedule"], str) else spec["work_schedule"]
            if schedule:
                schedule_str = format_schedule_compact(schedule, lang)
                lines.append(f"📅 {schedule_str}")
        except Exception:
            pass
    
    # Услуги
    spec_services = await api.get_specialist_services(spec["id"])
    active_services = [ss for ss in spec_services if ss.get("is_active", True)]
    
    lines.append("")
    if active_services:
        lines.append(t("admin:specialist:services_count", lang) % len(active_services))
        services = await api.get_services()
        services_map = {s["id"]: s["name"] for s in services}
        for ss in active_services:
            svc_name = services_map.get(ss["service_id"], "?")
            lines.append(f"  • {svc_name}")
    else:
        lines.append(t("admin:specialist:no_services", lang))
    
    return "\n".join(lines)


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    router = Router(name="specialists")
    logger.info("=== specialists.setup() called ===")
    
    # ==========================================================
    # LIST
    # ==========================================================
    
    async def show_list(message: Message, page: int = 0):
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)
        
        specialists = await api.get_specialists()
        users = await api.get_users()
        users_map = {u["id"]: u for u in users}
        
        total = len(specialists)
        
        if total == 0:
            text = f"👤 {t('admin:specialists:empty', lang)}"
        else:
            text = t("admin:specialists:list_title", lang) % total
        
        kb = specialists_list_inline(specialists, users_map, page, lang)
        await mc.show_inline_readonly(message, text, kb)
    
    router.show_list = show_list
    
    @router.callback_query(F.data.startswith("spec:page:"))
    async def list_page(callback: CallbackQuery):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        specialists = await api.get_specialists()
        users = await api.get_users()
        users_map = {u["id"]: u for u in users}
        
        total = len(specialists)
        
        if total == 0:
            text = f"👤 {t('admin:specialists:empty', lang)}"
        else:
            text = t("admin:specialists:list_title", lang) % total
        
        kb = specialists_list_inline(specialists, users_map, page, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "spec:list:0")
    async def list_first_page(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        specialists = await api.get_specialists()
        users = await api.get_users()
        users_map = {u["id"]: u for u in users}
        
        total = len(specialists)
        
        if total == 0:
            text = f"👤 {t('admin:specialists:empty', lang)}"
        else:
            text = t("admin:specialists:list_title", lang) % total
        
        kb = specialists_list_inline(specialists, users_map, 0, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "spec:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()
    
    @router.callback_query(F.data == "spec:back")
    async def list_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.back_to_reply(
            callback.message,
            admin_specialists(lang),
            title=t("admin:specialists:title", lang),
            menu_context="specialists",
        )
        await callback.answer()
    
    # ==========================================================
    # VIEW
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:view:"))
    async def view_specialist(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.clear()
        
        spec = await api.get_specialist(spec_id)
        if not spec:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        text = await build_specialist_view_text(spec, lang)
        kb = specialist_view_inline(spec, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ==========================================================
    # EDIT (delegation only)
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:edit:"))
    async def edit_specialist(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        await start_specialist_edit(
            mc=mc,
            callback=callback,
            state=state,
            spec_id=spec_id,
        )
    
    # ==========================================================
    # DELETE
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:delete:"))
    async def delete_confirm(callback: CallbackQuery):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        spec = await api.get_specialist(spec_id)
        if not spec:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        # Получаем имя
        name = spec.get("display_name")
        if not name:
            user = await api.get_user(spec["user_id"])
            name = _get_user_full_name(user) if user else "?"
        
        text = (
            t("admin:specialist:confirm_delete", lang) % name
            + "\n\n"
            + t("admin:specialist:delete_warning", lang)
        )
        kb = specialist_delete_confirm_inline(spec_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data.startswith("spec:delete_confirm:"))
    async def delete_execute(callback: CallbackQuery):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        ok = await api.delete_specialist(spec_id)
        if not ok:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        await callback.answer(t("admin:specialist:deleted", lang))
        
        # Вернуться к списку
        specialists = await api.get_specialists()
        users = await api.get_users()
        users_map = {u["id"]: u for u in users}
        
        total = len(specialists)
        
        if total == 0:
            text = f"👤 {t('admin:specialists:empty', lang)}"
        else:
            text = t("admin:specialists:list_title", lang) % total
        
        kb = specialists_list_inline(specialists, users_map, 0, lang)
        await mc.edit_inline(callback.message, text, kb)
    
    # ==========================================================
    # CREATE
    # ==========================================================
    
    async def start_create(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        
        # Проверяем наличие услуг
        services = await api.get_services()
        if not services:
            text = t("admin:specialist:error_no_services", lang)
            await mc.show_inline_readonly(message, text, specialist_cancel_inline(lang))
            return
        
        # Получаем пользователей и специалистов
        users = await api.get_users()
        specialists = await api.get_specialists()
        existing_user_ids = {s["user_id"] for s in specialists}
        
        # Проверяем есть ли свободные пользователи
        available = [u for u in users if u["id"] not in existing_user_ids]
        if not available:
            text = t("admin:specialist:error_no_users", lang)
            await mc.show_inline_readonly(message, text, specialist_cancel_inline(lang))
            return
        
        await state.set_state(SpecialistCreate.user)
        await state.update_data(
            lang=lang,
            selected_services=[],
            schedule=_specialist_default_schedule()
        )
        
        text = f"{t('admin:specialist:create_title', lang)}\n\n{t('admin:specialist:select_user', lang)}"
        kb = users_select_inline(users, existing_user_ids, lang)
        await mc.show_inline_input(message, text, kb)
    
    router.start_create = start_create
    
    # ---- Reply "Back" button во время FSM (escape hatch)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistCreate.user)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistCreate.search_phone)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistCreate.display_name)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistCreate.description)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistCreate.services)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistCreate.schedule)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistCreate.schedule_day)
    async def fsm_back_escape(message: Message, state: FSMContext):
        """Escape hatch: Reply Back во время FSM → отмена и возврат в меню."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.show(
            message,
            admin_specialists(lang),
            title=t("admin:specialists:title", lang),
            menu_context="specialists",
        )
    
    async def send_step(message: Message, text: str, kb: InlineKeyboardMarkup):
        try:
            await message.delete()
        except Exception:
            pass
        return await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)
    
    # ---- user pagination
    @router.callback_query(F.data.startswith("spec_create:user_page:"), SpecialistCreate.user)
    async def create_user_page(callback: CallbackQuery, state: FSMContext):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        users = await api.get_users()
        specialists = await api.get_specialists()
        existing_user_ids = {s["user_id"] for s in specialists}
        
        text = f"{t('admin:specialist:create_title', lang)}\n\n{t('admin:specialist:select_user', lang)}"
        kb = users_select_inline(users, existing_user_ids, lang, page=page)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- search phone button
    @router.callback_query(F.data == "spec_create:search", SpecialistCreate.user)
    async def create_search_start(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(SpecialistCreate.search_phone)
        
        text = t("admin:specialist:enter_phone", lang)
        kb = search_back_inline(lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- search phone input
    @router.message(SpecialistCreate.search_phone)
    async def create_search_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        phone = message.text.strip()
        
        # Ищем пользователя по телефону
        users = await api.get_users(phone=phone)
        specialists = await api.get_specialists()
        existing_user_ids = {s["user_id"] for s in specialists}
        
        # Фильтруем
        available = [u for u in users if u["id"] not in existing_user_ids]
        
        try:
            await message.delete()
        except Exception:
            pass
        
        if not available:
            text = t("admin:specialist:search_not_found", lang)
            kb = search_back_inline(lang)
            await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)
            return
        
        # Если найден один — сразу выбираем
        if len(available) == 1:
            user = available[0]
            user_name = _get_user_full_name(user)
            
            await state.update_data(
                user_id=user["id"],
                user_name=user_name
            )
            await state.set_state(SpecialistCreate.display_name)
            
            data = await state.get_data()
            text = build_progress_text(data, lang, "admin:specialist:enter_display_name")
            kb = specialist_skip_inline(lang)
            await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)
            return
        
        # Если найдено несколько — показываем список
        await state.set_state(SpecialistCreate.user)
        text = f"{t('admin:specialist:create_title', lang)}\n\n{t('admin:specialist:select_user', lang)}"
        kb = users_select_inline(available, set(), lang)
        await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)
    
    # ---- search back
    @router.callback_query(F.data == "spec_create:search_back")
    async def create_search_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(SpecialistCreate.user)
        
        users = await api.get_users()
        specialists = await api.get_specialists()
        existing_user_ids = {s["user_id"] for s in specialists}
        
        text = f"{t('admin:specialist:create_title', lang)}\n\n{t('admin:specialist:select_user', lang)}"
        kb = users_select_inline(users, existing_user_ids, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- user selected
    @router.callback_query(F.data.startswith("spec_create:user:"), SpecialistCreate.user)
    async def create_user_selected(callback: CallbackQuery, state: FSMContext):
        user_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        # Проверяем что пользователь ещё не специалист
        specialists = await api.get_specialists()
        existing_user_ids = {s["user_id"] for s in specialists}
        
        if user_id in existing_user_ids:
            await callback.answer(t("admin:specialist:error_user_is_specialist", lang), show_alert=True)
            return
        
        user = await api.get_user(user_id)
        if not user:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        user_name = _get_user_full_name(user)
        
        await state.update_data(
            user_id=user_id,
            user_name=user_name
        )
        await state.set_state(SpecialistCreate.display_name)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:specialist:enter_display_name")
        kb = specialist_skip_inline(lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- display_name skip
    @router.callback_query(F.data == "spec_create:skip", SpecialistCreate.display_name)
    async def skip_display_name(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        # display_name = None, будем использовать user_name
        await state.update_data(display_name=None)
        await state.set_state(SpecialistCreate.description)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:specialist:enter_description")
        kb = specialist_skip_inline(lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- display_name input
    @router.message(SpecialistCreate.display_name)
    async def create_display_name(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        display_name = message.text.strip() or None
        
        await state.update_data(display_name=display_name)
        await state.set_state(SpecialistCreate.description)
        
        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:specialist:enter_description")
        kb = specialist_skip_inline(lang)
        
        await send_step(message, text, kb)
    
    # ---- description skip
    @router.callback_query(F.data == "spec_create:skip", SpecialistCreate.description)
    async def skip_description(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.update_data(description=None)
        await state.set_state(SpecialistCreate.services)
        
        services = await api.get_services()
        data = await state.get_data()
        selected = set(data.get("selected_services", []))
        
        text = build_progress_text(data, lang, "admin:specialist:select_services")
        kb = services_multiselect_inline(services, selected, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- description input
    @router.message(SpecialistCreate.description)
    async def create_description(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        description = message.text.strip() or None
        
        await state.update_data(description=description)
        await state.set_state(SpecialistCreate.services)
        
        services = await api.get_services()
        data = await state.get_data()
        selected = set(data.get("selected_services", []))
        
        text = build_progress_text(data, lang, "admin:specialist:select_services")
        kb = services_multiselect_inline(services, selected, lang)
        
        await send_step(message, text, kb)
    
    # ---- services toggle
    @router.callback_query(F.data.startswith("spec_create:svc_toggle:"), SpecialistCreate.services)
    async def create_toggle_service(callback: CallbackQuery, state: FSMContext):
        svc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        selected = set(data.get("selected_services", []))
        
        if svc_id in selected:
            selected.discard(svc_id)
        else:
            selected.add(svc_id)
        
        await state.update_data(selected_services=list(selected))
        
        services = await api.get_services()
        text = build_progress_text(data, lang, "admin:specialist:select_services")
        kb = services_multiselect_inline(services, selected, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- services page
    @router.callback_query(F.data.startswith("spec_create:svc_page:"), SpecialistCreate.services)
    async def create_services_page(callback: CallbackQuery, state: FSMContext):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        selected = set(data.get("selected_services", []))
        
        services = await api.get_services()
        text = build_progress_text(data, lang, "admin:specialist:select_services")
        kb = services_multiselect_inline(services, selected, lang, page=page)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "spec_create:noop")
    async def create_noop(callback: CallbackQuery):
        await callback.answer()
    
    # ---- services done → schedule
    @router.callback_query(F.data == "spec_create:svc_done", SpecialistCreate.services)
    async def create_services_done(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        
        selected = set(data.get("selected_services", []))
        if not selected:
            await callback.answer(t("admin:specialist:error_no_services_selected", lang), show_alert=True)
            return
        
        await state.set_state(SpecialistCreate.schedule)
        
        schedule = data.get("schedule", _specialist_default_schedule())
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_sched")
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ==========================================================
    # SCHEDULE (CREATE)
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec_sched:day:"))
    async def schedule_day_selected(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("schedule", {})
        current = format_day_value(schedule.get(day), lang)
        
        await state.set_state(SpecialistCreate.schedule_day)
        await state.update_data(editing_day=day)
        
        day_name = t(f"day:{day}:full", lang)
        text = (
            f"{day_name}\n"
            f"{t('schedule:current', lang) % current}\n\n"
            f"{t('schedule:enter_time', lang)}"
        )
        
        kb = schedule_day_edit_inline(day, schedule, lang, prefix="spec_sched")
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.message(SpecialistCreate.schedule_day)
    async def process_schedule_time(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text_input = message.text.strip()
        
        result = parse_time_input(text_input)
        
        if result == "error":
            try:
                await message.delete()
            except Exception:
                pass
            err_msg = await message.answer(t("schedule:invalid", lang))
            await mc._add_inline_id(message.chat.id, err_msg.message_id)
            return
        
        data = await state.get_data()
        day = data.get("editing_day")
        schedule = data.get("schedule", {})
        schedule[day] = result
        
        await state.update_data(schedule=schedule)
        await state.set_state(SpecialistCreate.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_sched")
        await send_step(message, text, kb)
    
    @router.callback_query(F.data.startswith("spec_sched:dayoff:"))
    async def schedule_day_off(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("schedule", {})
        schedule[day] = None
        
        await state.update_data(schedule=schedule)
        await state.set_state(SpecialistCreate.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_sched")
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "spec_sched:back")
    async def schedule_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(SpecialistCreate.schedule)
        
        data = await state.get_data()
        schedule = data.get("schedule", {})
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_sched")
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ---- schedule save → CREATE SPECIALIST
    @router.callback_query(F.data == "spec_sched:save")
    async def schedule_save(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        
        # Создаём специалиста
        specialist = await api.create_specialist(
            user_id=data["user_id"],
            display_name=data.get("display_name"),
            description=data.get("description"),
            work_schedule=json.dumps(data.get("schedule", {}))
        )
        
        if not specialist:
            await callback.answer(t("common:error", lang), show_alert=True)
            return
        
        # Создаём связи с услугами
        selected = set(data.get("selected_services", []))
        for svc_id in selected:
            await api.add_specialist_service(specialist["id"], svc_id)
        
        # Имя для сообщения
        name = data.get("display_name") or data.get("user_name", "?")
        
        await state.clear()
        await callback.answer(t("admin:specialist:created", lang) % name)
        
        await mc.back_to_reply(
            callback.message,
            admin_specialists(lang),
            title=t("admin:specialists:title", lang),
            menu_context="specialists",
        )
    
    @router.callback_query(F.data == "spec_sched:cancel")
    async def schedule_cancel(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await callback.answer()
        await mc.back_to_reply(
            callback.message,
            admin_specialists(lang),
            title=t("admin:specialists:title", lang),
            menu_context="specialists",
        )
    
    # ---- cancel create
    @router.callback_query(F.data == "spec_create:cancel")
    async def cancel_create(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await callback.answer()
        await mc.back_to_reply(
            callback.message,
            admin_specialists(lang),
            title=t("admin:specialists:title", lang),
            menu_context="specialists",
        )
    
    # подключаем EDIT router
    router.include_router(setup_edit(mc, get_user_role))
    
    logger.info("=== specialists router configured ===")
    return router


