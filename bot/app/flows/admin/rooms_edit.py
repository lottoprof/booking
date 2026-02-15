"""
bot/app/flows/admin/rooms_edit.py

EDIT-FSM for Rooms (admin).
Вынесено из rooms.py без изменения бизнес-логики.

Правила:
- FSM в Redis (через общий aiogram storage)
- PATCH только diff (changes)
- Inline-only
- Не управляет Reply/menu_context (это делает rooms.py/admin_reply.py)

Особенности:
- Редактирование услуг — отдельный multi-select экран
- Нельзя сохранить без активных услуг
"""

import logging
import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.app.i18n.loader import DEFAULT_LANG, t, t_all
from bot.app.keyboards.admin import admin_rooms
from bot.app.utils.api import api
from bot.app.utils.pagination import build_nav_row
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)
PAGE_SIZE = 5


# ==============================================================
# FSM States (EDIT)
# ==============================================================

class RoomEdit(StatesGroup):
    """FSM для редактирования комнаты."""
    name = State()
    notes = State()
    order = State()
    services = State()


# ==============================================================
# Inline keyboards for EDIT
# ==============================================================

def room_edit_inline(room_id: int, lang: str) -> InlineKeyboardMarkup:
    """Экран редактирования комнаты."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:room:edit_name", lang),
                callback_data=f"room:edit_name:{room_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:room:edit_notes", lang),
                callback_data=f"room:edit_notes:{room_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("admin:room:edit_order", lang),
                callback_data=f"room:edit_order:{room_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:room:edit_services", lang),
                callback_data=f"room:edit_services:{room_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("common:save", lang),
                callback_data=f"room:save:{room_id}"
            ),
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data=f"room:view:{room_id}"
            ),
        ],
    ])


def room_edit_cancel_inline(room_id: int, lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при редактировании поля."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"room:edit:{room_id}"
        )
    ]])


def services_edit_multiselect_inline(
    services: list[dict],
    active_service_ids: set[int],
    room_id: int,
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
                callback_data=f"room:svc_toggle:{room_id}:{svc['id']}"
            )
        ])

    # Пагинация
    nav = build_nav_row(page, total_pages, f"room:svc_page:{room_id}:{{p}}", "room:noop", lang)
    if nav:
        buttons.append(nav)

    # Сохранить (с количеством)
    count = len(active_service_ids)
    save_text = t("admin:room:services_save", lang) % count

    buttons.append([
        InlineKeyboardButton(
            text=save_text,
            callback_data=f"room:svc_save:{room_id}" if count > 0 else "room:noop"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data=f"room:edit:{room_id}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==============================================================
# Helpers: texts
# ==============================================================

async def build_room_view_text(room: dict, lang: str) -> str:
    """Текст карточки комнаты (дублируем минимально)."""
    lines = [t("admin:room:view_title", lang) % room["name"], ""]

    location = await api.get_location(room["location_id"])
    loc_name = location["name"] if location else "?"
    lines.append(t("admin:room:location", lang) % loc_name)

    if room.get("display_order") is not None:
        lines.append(t("admin:room:order", lang) % room["display_order"])

    if room.get("notes"):
        lines.append(f"📝 {room['notes']}")

    service_rooms = await api.get_service_rooms_by_room(room["id"])
    active_services = [sr for sr in service_rooms if sr.get("is_active", True)]

    lines.append("")
    if active_services:
        lines.append(t("admin:room:services_count", lang) % len(active_services))
        services = await api.get_services()
        services_map = {s["id"]: s["name"] for s in services}
        for sr in active_services:
            svc_name = services_map.get(sr["service_id"], "?")
            lines.append(f"  • {svc_name}")
    else:
        lines.append(t("admin:room:no_services", lang))

    return "\n".join(lines)


def build_room_edit_text(room: dict, changes: dict, lang: str) -> str:
    """
    Текст экрана редактирования.
    Показывает текущие значения + изменения из changes.
    """
    name = changes.get("name", room.get("name", ""))
    notes = changes.get("notes", room.get("notes"))
    display_order = changes.get("display_order", room.get("display_order"))

    lines = [t("admin:room:edit_title", lang), ""]
    lines.append(f"🚪 {name}")

    if display_order is not None:
        lines.append(f"↕️ {display_order}")

    if notes:
        lines.append(f"📝 {notes}")

    if changes:
        lines.append("")
        changed_names = _get_changed_field_names(changes, lang)
        if changed_names:
            lines.append("✏️ " + ", ".join(changed_names))

    return "\n".join(lines)


def _get_changed_field_names(changes: dict, lang: str) -> list[str]:
    """Возвращает читаемые имена изменённых полей."""
    field_map = {
        "name": "admin:room:edit_name",
        "notes": "admin:room:edit_notes",
        "display_order": "admin:room:edit_order",
    }

    names = []
    for field, key in field_map.items():
        if field in changes:
            name = t(key, lang)
            for emoji in ["✏️ ", "📝 ", "↕️ "]:
                name = name.replace(emoji, "")
            names.append(name)

    return names


# ==============================================================
# Entry point (called from rooms.py delegate)
# ==============================================================

async def start_room_edit(*, mc, callback: CallbackQuery, state: FSMContext, room_id: int) -> None:
    """
    Entry point редактирования комнаты.

    ВАЖНО:
    - обработчик room:edit:{id} находится в rooms.py и просто делегирует сюда.
    - здесь только инициализация + показ edit-экрана.
    """
    lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

    room = await api.get_room(room_id)
    if not room:
        await callback.answer(t("common:error", lang), show_alert=True)
        return

    data = await state.get_data()

    # Если новый вход или другой room_id — инициализируем заново
    if data.get("edit_room_id") != room_id:
        await state.update_data(
            edit_room_id=room_id,
            original=room,
            changes={}
        )
        data = await state.get_data()

    changes = data.get("changes", {})
    text = build_room_edit_text(room, changes, lang)
    kb = room_edit_inline(room_id, lang)

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

    router = Router(name="rooms_edit")
    logger.info("=== rooms_edit.setup() called ===")

    # ==========================================================
    # Reply "Back" escape hatch for EDIT FSM
    # ==========================================================

    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomEdit.name)
    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomEdit.notes)
    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomEdit.order)
    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomEdit.services)
    async def edit_fsm_back_escape(message: Message, state: FSMContext):
        """Escape hatch: Reply Back во время Edit FSM → отмена и возврат."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.show(
            message,
            admin_rooms(lang),
            title=t("admin:rooms:title", lang),
            menu_context="rooms",
        )

    # ==========================================================
    # EDIT: name
    # ==========================================================

    @router.callback_query(F.data.startswith("room:edit_name:"))
    async def edit_name_start(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(RoomEdit.name)

        text = t("admin:room:enter_name", lang)
        kb = room_edit_cancel_inline(room_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(RoomEdit.name)
    async def edit_name_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()

        if len(name) < 2:
            data = await state.get_data()
            room_id = data.get("edit_room_id")
            await mc.show_inline_input(message, t("admin:room:error_name", lang), room_edit_cancel_inline(room_id, lang))
            return

        data = await state.get_data()
        room_id = data.get("edit_room_id")
        changes = data.get("changes", {})
        changes["name"] = name

        await state.update_data(changes=changes)
        await state.set_state(None)

        room = data.get("original", {})
        text = build_room_edit_text(room, changes, lang)
        kb = room_edit_inline(room_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: notes
    # ==========================================================

    @router.callback_query(F.data.startswith("room:edit_notes:"))
    async def edit_notes_start(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(RoomEdit.notes)

        text = t("admin:room:enter_notes", lang)
        kb = room_edit_cancel_inline(room_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(RoomEdit.notes)
    async def edit_notes_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        notes = message.text.strip()

        data = await state.get_data()
        room_id = data.get("edit_room_id")
        changes = data.get("changes", {})
        changes["notes"] = notes if notes else None

        await state.update_data(changes=changes)
        await state.set_state(None)

        room = data.get("original", {})
        text = build_room_edit_text(room, changes, lang)
        kb = room_edit_inline(room_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: display_order
    # ==========================================================

    @router.callback_query(F.data.startswith("room:edit_order:"))
    async def edit_order_start(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(RoomEdit.order)

        text = t("admin:room:enter_order", lang)
        kb = room_edit_cancel_inline(room_id, lang)

        await mc.edit_inline_input(callback.message, text, kb)
        await callback.answer()

    @router.message(RoomEdit.order)
    async def edit_order_process(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        try:
            display_order = int(message.text.strip())
        except ValueError:
            data = await state.get_data()
            room_id = data.get("edit_room_id")
            await mc.show_inline_input(message, t("admin:room:error_order", lang), room_edit_cancel_inline(room_id, lang))
            return

        data = await state.get_data()
        room_id = data.get("edit_room_id")
        changes = data.get("changes", {})
        changes["display_order"] = display_order

        await state.update_data(changes=changes)
        await state.set_state(None)

        room = data.get("original", {})
        text = build_room_edit_text(room, changes, lang)
        kb = room_edit_inline(room_id, lang)

        await mc.show_inline_readonly(message, text, kb)

    # ==========================================================
    # EDIT: services (multi-select)
    # ==========================================================

    @router.callback_query(F.data.startswith("room:edit_services:"))
    async def edit_services_start(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.set_state(RoomEdit.services)

        # Получаем текущие активные услуги комнаты
        service_rooms = await api.get_service_rooms_by_room(room_id)
        active_ids = {sr["service_id"] for sr in service_rooms if sr.get("is_active", True)}

        await state.update_data(edit_services=list(active_ids))

        services = await api.get_services()
        text = t("admin:room:services_title", lang)
        kb = services_edit_multiselect_inline(services, active_ids, room_id, lang)

        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("room:svc_toggle:"), RoomEdit.services)
    async def edit_services_toggle(callback: CallbackQuery, state: FSMContext):
        parts = callback.data.split(":")
        room_id = int(parts[2])
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
        text = t("admin:room:services_title", lang)
        kb = services_edit_multiselect_inline(services, active_ids, room_id, lang)

        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("room:svc_page:"), RoomEdit.services)
    async def edit_services_page(callback: CallbackQuery, state: FSMContext):
        parts = callback.data.split(":")
        room_id = int(parts[2])
        page = int(parts[3])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        active_ids = set(data.get("edit_services", []))

        services = await api.get_services()
        text = t("admin:room:services_title", lang)
        kb = services_edit_multiselect_inline(services, active_ids, room_id, lang, page=page)

        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("room:svc_save:"), RoomEdit.services)
    async def edit_services_save(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        new_active_ids = set(data.get("edit_services", []))

        if not new_active_ids:
            await callback.answer(t("admin:room:error_no_services_selected", lang), show_alert=True)
            return

        # Получаем текущие service_rooms
        service_rooms = await api.get_service_rooms_by_room(room_id)
        existing_map = {sr["service_id"]: sr for sr in service_rooms}

        all_services = await api.get_services()
        all_svc_ids = {s["id"] for s in all_services}

        # Синхронизируем:
        # - если svc_id в new_active_ids и нет записи → создаём
        # - если svc_id в new_active_ids и есть запись is_active=0 → PATCH is_active=1
        # - если svc_id не в new_active_ids и есть запись is_active=1 → PATCH is_active=0

        for svc_id in all_svc_ids:
            sr = existing_map.get(svc_id)

            if svc_id in new_active_ids:
                if sr is None:
                    await api.create_service_room(room_id, svc_id)
                elif not sr.get("is_active", True):
                    await api.update_service_room(sr["id"], is_active=True)
            else:
                if sr is not None and sr.get("is_active", True):
                    await api.update_service_room(sr["id"], is_active=False)

        await state.set_state(None)

        # Возвращаемся на экран редактирования
        room = data.get("original", {})
        changes = data.get("changes", {})
        text = build_room_edit_text(room, changes, lang)
        kb = room_edit_inline(room_id, lang)

        await mc.edit_inline(callback.message, text, kb)
        await callback.answer(t("admin:room:saved", lang))

    # ==========================================================
    # SAVE: применить все изменения полей
    # ==========================================================

    @router.callback_query(F.data.startswith("room:save:"))
    async def save_room(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        changes = data.get("changes", {})

        if not changes:
            await callback.answer(t("admin:room:no_changes", lang))
            return

        result = await api.update_room(room_id, **changes)
        if not result:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        await state.clear()
        await callback.answer(t("admin:room:saved", lang))

        # Показать обновлённую карточку
        room = await api.get_room(room_id)
        if room:
            # Импортируем здесь, чтобы избежать circular import
            from .rooms import room_view_inline
            text = await build_room_view_text(room, lang)
            kb = room_view_inline(room, lang)
            await mc.edit_inline(callback.message, text, kb)

    logger.info("=== rooms_edit router configured ===")
    return router
