"""
bot/app/flows/admin/specialists_edit.py

EDIT-FSM for Specialists (admin).
Вынесено из specialists.py без изменения бизнес-логики.

Правила:
- FSM в Redis (через общий aiogram storage)
- PATCH только diff (changes)
- Inline-only
- Не управляет Reply/menu_context (это делает specialists.py/admin_reply.py)

Особенности:
- Редактирование услуг — отдельный multi-select экран
- Нельзя сохранить без активных услуг
- Фото — заглушка (v2)
"""

import logging
import json
import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, t_all, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.utils.schedule_helper import (
    parse_time_input,
    format_day_value,
    format_schedule_compact,
    default_schedule,
)
from bot.app.keyboards.schedule import (
    schedule_days_inline,
    schedule_day_edit_inline,
)

logger = logging.getLogger(__name__)
PAGE_SIZE = 5


# ==============================================================
# FSM States (EDIT)
# ==============================================================

class SpecialistEdit(StatesGroup):
    """FSM для редактирования специалиста."""
    name = State()
    description = State()
    photo = State()
    schedule = State()
    schedule_day = State()
    services = State()


# ==============================================================
# Inline keyboards for EDIT
# ==============================================================

def specialist_edit_inline(spec_id: int, lang: str) -> InlineKeyboardMarkup:
    """Экран редактирования специалиста."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:specialist:edit_name", lang),
                callback_data=f"spec:edit_name:{spec_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:specialist:edit_description", lang),
                callback_data=f"spec:edit_desc:{spec_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("admin:specialist:photo_stub", lang),
                callback_data=f"spec:edit_photo:{spec_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:specialist:edit_schedule", lang),
                callback_data=f"spec:edit_sched:{spec_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("admin:specialist:edit_services", lang),
                callback_data=f"spec:edit_services:{spec_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("common:save", lang),
                callback_data=f"spec:save:{spec_id}"
            ),
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data=f"spec:view:{spec_id}"
            ),
        ],
    ])


def specialist_edit_cancel_inline(spec_id: int, lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при редактировании поля."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"spec:edit:{spec_id}"
        )
    ]])


def services_edit_multiselect_inline(
    services: list[dict],
    active_service_ids: set[int],
    spec_id: int,
    lang: str,
    page: int = 0
) -> InlineKeyboardMarkup:
    """
    Мульти-выбор услуг при редактировании.
    ✅ — активна, ⬜ — неактивна.
    """
    total = len(services)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = services[start:end]
    
    buttons = []
    
    for svc in page_items:
        is_active = svc["id"] in active_service_ids
        icon = "✅" if is_active else "⬜"
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {svc['name']}",
                callback_data=f"spec:svc_toggle:{spec_id}:{svc['id']}"
            )
        ])
    
    # Пагинация
    if total_pages > 1:
        nav_row = []
        
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"spec:svc_page:{spec_id}:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="spec:noop"
            ))
        
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="spec:noop"
        ))
        
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"spec:svc_page:{spec_id}:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="spec:noop"
            ))
        
        buttons.append(nav_row)
    
    # Сохранить (с количеством)
    count = len(active_service_ids)
    save_text = t("admin:specialist:services_save", lang) % count
    
    buttons.append([
        InlineKeyboardButton(
            text=save_text,
            callback_data=f"spec:svc_save:{spec_id}" if count > 0 else "spec:noop"
        )
    ])
    
    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"spec:edit:{spec_id}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==============================================================
# Helpers: texts
# ==============================================================

def _get_user_full_name(user: dict) -> str:
    """Получить полное имя пользователя."""
    first = user.get("first_name") or ""
    last = user.get("last_name") or ""
    return f"{first} {last}".strip() or "?"


async def build_specialist_view_text(spec: dict, lang: str) -> str:
    """Текст карточки специалиста."""
    user = await api.get_user(spec["user_id"])
    
    name = spec.get("display_name")
    if not name and user:
        name = _get_user_full_name(user)
    name = name or "?"
    
    lines = [t("admin:specialist:view_title", lang) % name, ""]
    
    if user and user.get("phone"):
        lines.append(t("admin:specialist:phone", lang) % user["phone"])
    else:
        lines.append(t("admin:specialist:no_phone", lang))
    
    if spec.get("description"):
        lines.append(f"📝 {spec['description']}")
    
    if spec.get("work_schedule"):
        try:
            schedule = json.loads(spec["work_schedule"]) if isinstance(spec["work_schedule"], str) else spec["work_schedule"]
            if schedule:
                schedule_str = format_schedule_compact(schedule, lang)
                lines.append(f"📅 {schedule_str}")
        except Exception:
            pass
    
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


def build_specialist_edit_text(spec: dict, changes: dict, lang: str) -> str:
    """
    Текст экрана редактирования.
    Показывает текущие значения + изменения из changes.
    """
    name = changes.get("display_name", spec.get("display_name", ""))
    description = changes.get("description", spec.get("description"))
    
    # График
    if "work_schedule" in changes:
        schedule = changes["work_schedule"]
    else:
        try:
            ws = spec.get("work_schedule", "{}")
            schedule = json.loads(ws) if isinstance(ws, str) else ws
        except Exception:
            schedule = {}
    
    lines = [t("admin:specialist:edit_title", lang), ""]
    
    if name:
        lines.append(f"📛 {name}")
    
    if description:
        lines.append(f"📝 {description}")
    
    if schedule:
        schedule_str = format_schedule_compact(schedule, lang)
        lines.append(f"📅 {schedule_str}")
    
    # Показываем что изменено
    if changes:
        changed_names = _get_changed_field_names(changes, lang)
        if changed_names:
            lines.append("")
            lines.append("✏️ " + ", ".join(changed_names))
    
    return "\n".join(lines)


def _get_changed_field_names(changes: dict, lang: str) -> list[str]:
    """Возвращает читаемые имена изменённых полей."""
    field_map = {
        "display_name": "admin:specialist:edit_name",
        "description": "admin:specialist:edit_description",
        "work_schedule": "admin:specialist:edit_schedule",
    }
    
    names = []
    for field, key in field_map.items():
        if field in changes:
            name = t(key, lang)
            for emoji in ["✏️ ", "📝 ", "📅 ", "📷 "]:
                name = name.replace(emoji, "")
            names.append(name)
    
    return names


# ==============================================================
# Entry point (called from specialists.py delegate)
# ==============================================================

async def start_specialist_edit(
    *,
    mc,
    callback: CallbackQuery,
    state: FSMContext,
    spec_id: int
) -> None:
    """
    Entry point редактирования специалиста.
    """
    lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
    
    spec = await api.get_specialist(spec_id)
    if not spec:
        await callback.answer(t("common:error", lang), show_alert=True)
        return
    
    data = await state.get_data()
    
    # Если новый вход или другой spec_id — инициализируем заново
    if data.get("edit_spec_id") != spec_id:
        await state.update_data(
            edit_spec_id=spec_id,
            original=spec,
            changes={}
        )
        data = await state.get_data()
    
    changes = data.get("changes", {})
    text = build_specialist_edit_text(spec, changes, lang)
    kb = specialist_edit_inline(spec_id, lang)
    
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
    
    router = Router(name="specialists_edit")
    logger.info("=== specialists_edit.setup() called ===")
    
    # Импортируем admin_specialists из keyboards
    from bot.app.keyboards.admin import admin_specialists
    
    # ==========================================================
    # Reply "Back" escape hatch for EDIT FSM
    # ==========================================================
    
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistEdit.name)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistEdit.description)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistEdit.photo)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistEdit.schedule)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistEdit.schedule_day)
    @router.message(F.text.in_(t_all("admin:specialists:back")), SpecialistEdit.services)
    async def edit_fsm_back_escape(message: Message, state: FSMContext):
        """Escape hatch: Reply Back во время Edit FSM → отмена и возврат."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.show(
            message,
            admin_specialists(lang),
            title=t("admin:specialists:title", lang),
            menu_context="specialists",
        )
    
    # ==========================================================
    # EDIT: display_name
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:edit_name:"))
    async def edit_name_start(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(SpecialistEdit.name)
        
        text = t("admin:specialist:enter_display_name", lang)
        kb = specialist_edit_cancel_inline(spec_id, lang)
        
        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()
    
    @router.message(SpecialistEdit.name)
    async def edit_name_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip() or None
        
        data = await state.get_data()
        spec_id = data.get("edit_spec_id")
        changes = data.get("changes", {})
        changes["display_name"] = name
        
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        spec = data.get("original", {})
        text = build_specialist_edit_text(spec, changes, lang)
        kb = specialist_edit_inline(spec_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: description
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:edit_desc:"))
    async def edit_desc_start(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(SpecialistEdit.description)
        
        text = t("admin:specialist:enter_description", lang)
        kb = specialist_edit_cancel_inline(spec_id, lang)
        
        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()
    
    @router.message(SpecialistEdit.description)
    async def edit_desc_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        description = message.text.strip() or None
        
        data = await state.get_data()
        spec_id = data.get("edit_spec_id")
        changes = data.get("changes", {})
        changes["description"] = description
        
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        spec = data.get("original", {})
        text = build_specialist_edit_text(spec, changes, lang)
        kb = specialist_edit_inline(spec_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: photo (STUB)
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:edit_photo:"))
    async def edit_photo_stub(callback: CallbackQuery, state: FSMContext):
        """Заглушка для фото — функционал в v2."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await callback.answer(t("admin:specialist:photo_stub", lang), show_alert=True)
    
    # ==========================================================
    # EDIT: schedule
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:edit_sched:"))
    async def edit_sched_start(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        changes = data.get("changes", {})
        spec = data.get("original", {})
        
        # Берём график из changes или из original
        if "work_schedule" in changes:
            schedule = changes["work_schedule"]
        else:
            try:
                ws = spec.get("work_schedule", "{}")
                schedule = json.loads(ws) if isinstance(ws, str) else ws
            except Exception:
                schedule = default_schedule()
        
        await state.set_state(SpecialistEdit.schedule)
        await state.update_data(edit_schedule=schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_edit_sched")
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data.startswith("spec_edit_sched:day:"))
    async def edit_sched_day_selected(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        current = format_day_value(schedule.get(day), lang)
        
        await state.set_state(SpecialistEdit.schedule_day)
        await state.update_data(editing_day=day)
        
        day_name = t(f"day:{day}:full", lang)
        text = (
            f"{day_name}\n"
            f"{t('schedule:current', lang) % current}\n\n"
            f"{t('schedule:enter_time', lang)}"
        )
        
        kb = schedule_day_edit_inline(day, schedule, lang, prefix="spec_edit_sched")
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
    
    @router.message(SpecialistEdit.schedule_day)
    async def edit_sched_time_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text_input = message.text.strip()
        
        result = parse_time_input(text_input)
        
        if result == "error":
            data = await state.get_data()
            spec_id = data.get("edit_spec_id")
            await mc.show_inline_input(message, t("schedule:invalid", lang), specialist_edit_cancel_inline(spec_id, lang))
            return
        
        data = await state.get_data()
        day = data.get("editing_day")
        schedule = data.get("edit_schedule", {})
        schedule[day] = result
        
        await state.update_data(edit_schedule=schedule)
        await state.set_state(SpecialistEdit.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_edit_sched")

        await mc.show_inline_readonly(message, text, kb)
    
    @router.callback_query(F.data.startswith("spec_edit_sched:dayoff:"))
    async def edit_sched_day_off(callback: CallbackQuery, state: FSMContext):
        day = callback.data.split(":")[2]
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        schedule[day] = None
        
        await state.update_data(edit_schedule=schedule)
        await state.set_state(SpecialistEdit.schedule)
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_edit_sched")
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
    
    @router.callback_query(F.data == "spec_edit_sched:back")
    async def edit_sched_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(SpecialistEdit.schedule)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        
        text = t("schedule:title", lang)
        kb = schedule_days_inline(schedule, lang, prefix="spec_edit_sched")
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
    
    @router.callback_query(F.data == "spec_edit_sched:save")
    async def edit_sched_save(callback: CallbackQuery, state: FSMContext):
        """Сохранить график в changes и вернуться на экран редактирования."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        schedule = data.get("edit_schedule", {})
        spec_id = data.get("edit_spec_id")
        changes = data.get("changes", {})
        
        changes["work_schedule"] = schedule
        await state.update_data(changes=changes)
        await state.set_state(None)
        
        spec = data.get("original", {})
        text = build_specialist_edit_text(spec, changes, lang)
        kb = specialist_edit_inline(spec_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data == "spec_edit_sched:cancel")
    async def edit_sched_cancel(callback: CallbackQuery, state: FSMContext):
        """Отменить редактирование графика."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        spec_id = data.get("edit_spec_id")
        changes = data.get("changes", {})
        spec = data.get("original", {})
        
        await state.set_state(None)
        
        text = build_specialist_edit_text(spec, changes, lang)
        kb = specialist_edit_inline(spec_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    # ==========================================================
    # EDIT: services (multi-select)
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:edit_services:"))
    async def edit_services_start(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        await state.set_state(SpecialistEdit.services)
        
        # Получаем текущие активные услуги специалиста
        spec_services = await api.get_specialist_services(spec_id)
        active_ids = {ss["service_id"] for ss in spec_services if ss.get("is_active", True)}
        
        await state.update_data(edit_services=list(active_ids))
        
        services = await api.get_services()
        text = t("admin:specialist:services_title", lang)
        kb = services_edit_multiselect_inline(services, active_ids, spec_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()
    
    @router.callback_query(F.data.startswith("spec:svc_toggle:"), SpecialistEdit.services)
    async def edit_services_toggle(callback: CallbackQuery, state: FSMContext):
        parts = callback.data.split(":")
        spec_id = int(parts[2])
        svc_id = int(parts[3])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        active_ids = set(data.get("edit_services", []))
        
        if svc_id in active_ids:
            active_ids.discard(svc_id)
        else:
            active_ids.add(svc_id)
        
        await state.update_data(edit_services=list(active_ids))
        
        services = await api.get_services()
        text = t("admin:specialist:services_title", lang)
        kb = services_edit_multiselect_inline(services, active_ids, spec_id, lang)
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
    
    @router.callback_query(F.data.startswith("spec:svc_page:"), SpecialistEdit.services)
    async def edit_services_page(callback: CallbackQuery, state: FSMContext):
        parts = callback.data.split(":")
        spec_id = int(parts[2])
        page = int(parts[3])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        active_ids = set(data.get("edit_services", []))
        
        services = await api.get_services()
        text = t("admin:specialist:services_title", lang)
        kb = services_edit_multiselect_inline(services, active_ids, spec_id, lang, page=page)
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
    
    @router.callback_query(F.data.startswith("spec:svc_save:"), SpecialistEdit.services)
    async def edit_services_save(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        new_active_ids = set(data.get("edit_services", []))
        
        if not new_active_ids:
            await callback.answer(
                t("admin:specialist:error_no_services_selected", lang),
                show_alert=True
            )
            return
        
        # Получаем текущие specialist_services
        spec_services = await api.get_specialist_services(spec_id)
        existing_map = {ss["service_id"]: ss for ss in spec_services}
        
        all_services = await api.get_services()
        all_svc_ids = {s["id"] for s in all_services}
        
        # Синхронизируем:
        for svc_id in all_svc_ids:
            ss = existing_map.get(svc_id)
            
            if svc_id in new_active_ids:
                if ss is None:
                    # Создаём новую связь
                    await api.add_specialist_service(spec_id, svc_id)
                elif not ss.get("is_active", True):
                    # Активируем существующую
                    await api.update_specialist_service(spec_id, svc_id, is_active=True)
            else:
                if ss is not None and ss.get("is_active", True):
                    # Деактивируем
                    await api.update_specialist_service(spec_id, svc_id, is_active=False)
        
        await state.set_state(None)
        
        # Возвращаемся на экран редактирования
        spec = data.get("original", {})
        changes = data.get("changes", {})
        text = build_specialist_edit_text(spec, changes, lang)
        kb = specialist_edit_inline(spec_id, lang)
        
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer(t("admin:specialist:saved", lang))
    
    # ==========================================================
    # SAVE: применить все изменения полей
    # ==========================================================
    
    @router.callback_query(F.data.startswith("spec:save:"))
    async def save_specialist(callback: CallbackQuery, state: FSMContext):
        spec_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        
        data = await state.get_data()
        changes = data.get("changes", {})
        
        if not changes:
            await callback.answer(t("admin:specialist:no_changes", lang))
            return
        
        # Подготовка данных для PATCH
        patch_data = {}
        
        if "display_name" in changes:
            patch_data["display_name"] = changes["display_name"]
        if "description" in changes:
            patch_data["description"] = changes["description"]
        if "work_schedule" in changes:
            patch_data["work_schedule"] = json.dumps(changes["work_schedule"])
        
        if patch_data:
            result = await api.update_specialist(spec_id, **patch_data)
            if not result:
                await callback.answer(t("common:error", lang), show_alert=True)
                return
        
        await state.clear()
        await callback.answer(t("admin:specialist:saved", lang))
        
        # Показать обновлённую карточку
        spec = await api.get_specialist(spec_id)
        if spec:
            from .specialists import specialist_view_inline
            text = await build_specialist_view_text(spec, lang)
            kb = specialist_view_inline(spec, lang)
            await mc.edit_inline(callback.message, text, kb)
    
    logger.info("=== specialists_edit router configured ===")
    return router

