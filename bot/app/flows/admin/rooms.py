"""
bot/app/flows/admin/rooms.py
FSM создания комнаты + список / просмотр / удаление.
EDIT вынесен в rooms_edit.py (делегирование).

Ответственность файла:
- LIST (inline)
- VIEW
- DELETE
- CREATE (FSM, Redis) — с обязательным выбором услуг
- делегирование EDIT
"""

import logging
import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.app.i18n.loader import t, t_all, DEFAULT_LANG
from bot.app.utils.state import user_lang
from bot.app.utils.api import api
from bot.app.keyboards.admin import admin_rooms

# EDIT entry point
from .rooms_edit import start_room_edit, setup as setup_edit

logger = logging.getLogger(__name__)
PAGE_SIZE = 5


# ==============================================================
# FSM: CREATE
# ==============================================================

class RoomCreate(StatesGroup):
    location = State()
    name = State()
    notes = State()
    services = State()


# ==============================================================
# Inline keyboards
# ==============================================================

def room_cancel_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при создании."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="room_create:cancel"
        )
    ]])


def room_skip_inline(lang: str) -> InlineKeyboardMarkup:
    """Кнопка пропустить + отмена."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:skip", lang),
                callback_data="room_create:skip"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:cancel", lang),
                callback_data="room_create:cancel"
            )
        ]
    ])


def locations_select_inline(
    locations: list[dict],
    lang: str
) -> InlineKeyboardMarkup:
    """Выбор локации при создании комнаты."""
    buttons = []

    for loc in locations:
        buttons.append([
            InlineKeyboardButton(
                text=f"📍 {loc['name']}",
                callback_data=f"room_create:loc:{loc['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text=t("common:cancel", lang),
            callback_data="room_create:cancel"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def services_multiselect_inline(
    services: list[dict],
    selected_ids: set[int],
    lang: str,
    page: int = 0,
    prefix: str = "room_create"
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
    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"{prefix}:svc_page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data=f"{prefix}:noop"
            ))

        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data=f"{prefix}:noop"
        ))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"{prefix}:svc_page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data=f"{prefix}:noop"
            ))

        buttons.append(nav_row)

    # Готово (с количеством)
    count = len(selected_ids)
    done_text = t("admin:room:services_selected", lang) % count

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


def rooms_list_inline(
    rooms: list[dict],
    locations_map: dict[int, str],
    page: int,
    lang: str
) -> InlineKeyboardMarkup:
    """Список комнат с пагинацией."""
    total = len(rooms)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = rooms[start:end]

    buttons = []

    for room in page_items:
        loc_name = locations_map.get(room["location_id"], "?")
        # "🚪 Кабинет 1 (Центр)"
        text = t("admin:rooms:item", lang) % (room["name"], loc_name)
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"room:view:{room['id']}"
            )
        ])

    # Пагинация
    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"room:page:{page - 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="room:noop"
            ))

        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="room:noop"
        ))

        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"room:page:{page + 1}"
            ))
        else:
            nav_row.append(InlineKeyboardButton(
                text=" ",
                callback_data="room:noop"
            ))

        buttons.append(nav_row)

    # Назад
    buttons.append([
        InlineKeyboardButton(
            text=t("common:back", lang),
            callback_data="room:back"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def room_view_inline(room: dict, lang: str) -> InlineKeyboardMarkup:
    """Карточка просмотра комнаты."""
    room_id = room["id"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:room:edit", lang),
                callback_data=f"room:edit:{room_id}"
            ),
            InlineKeyboardButton(
                text=t("admin:room:delete", lang),
                callback_data=f"room:delete:{room_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=t("common:back", lang),
                callback_data="room:list:0"
            )
        ]
    ])


def room_delete_confirm_inline(room_id: int, lang: str) -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("common:yes", lang),
                callback_data=f"room:delete_confirm:{room_id}"
            ),
            InlineKeyboardButton(
                text=t("common:no", lang),
                callback_data=f"room:view:{room_id}"
            )
        ]
    ])


# ==============================================================
# Reply keyboard
# ==============================================================

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def admin_rooms(lang: str) -> ReplyKeyboardMarkup:
    """Меню комнат."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("admin:rooms:list", lang)),
                KeyboardButton(text=t("admin:rooms:create", lang)),
            ],
            [
                KeyboardButton(text=t("admin:rooms:back", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ==============================================================
# Helpers
# ==============================================================

def build_progress_text(data: dict, lang: str, prompt_key: str) -> str:
    """Текст с прогрессом создания комнаты."""
    lines = [t("admin:room:create_title", lang), ""]

    if data.get("location_name"):
        lines.append(f"📍 {data['location_name']}")
    if data.get("name"):
        lines.append(f"🚪 {data['name']}")
    if data.get("notes"):
        lines.append(f"📝 {data['notes']}")

    selected_services = data.get("selected_services", [])
    if selected_services:
        lines.append(f"🛎 Услуги: {len(selected_services)}")

    lines.append("")
    lines.append(t(prompt_key, lang))
    return "\n".join(lines)


async def build_room_view_text(room: dict, lang: str) -> str:
    """Текст карточки комнаты."""
    lines = [t("admin:room:view_title", lang) % room["name"], ""]

    # Локация
    location = await api.get_location(room["location_id"])
    loc_name = location["name"] if location else "?"
    lines.append(t("admin:room:location", lang) % loc_name)

    # Порядок
    if room.get("display_order") is not None:
        lines.append(t("admin:room:order", lang) % room["display_order"])

    # Заметки
    if room.get("notes"):
        lines.append(f"📝 {room['notes']}")

    # Услуги
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


# ==============================================================
# Setup
# ==============================================================

def setup(mc, get_user_role):
    router = Router(name="rooms")
    logger.info("=== rooms.setup() called ===")

    # ==========================================================
    # LIST
    # ==========================================================

    async def show_list(message: Message, page: int = 0):
        tg_id = message.from_user.id
        lang = user_lang.get(tg_id, DEFAULT_LANG)

        rooms = await api.get_rooms()
        locations = await api.get_locations()
        locations_map = {loc["id"]: loc["name"] for loc in locations}

        total = len(rooms)

        if total == 0:
            text = f"🚪 {t('admin:rooms:empty', lang)}"
        else:
            text = t("admin:rooms:list_title", lang) % total

        kb = rooms_list_inline(rooms, locations_map, page, lang)
        await mc.show_inline_readonly(message, text, kb)

    router.show_list = show_list

    @router.callback_query(F.data.startswith("room:page:"))
    async def list_page(callback: CallbackQuery):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        rooms = await api.get_rooms()
        locations = await api.get_locations()
        locations_map = {loc["id"]: loc["name"] for loc in locations}

        total = len(rooms)

        if total == 0:
            text = f"🚪 {t('admin:rooms:empty', lang)}"
        else:
            text = t("admin:rooms:list_title", lang) % total

        kb = rooms_list_inline(rooms, locations_map, page, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "room:list:0")
    async def list_first_page(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        rooms = await api.get_rooms()
        locations = await api.get_locations()
        locations_map = {loc["id"]: loc["name"] for loc in locations}

        total = len(rooms)

        if total == 0:
            text = f"🚪 {t('admin:rooms:empty', lang)}"
        else:
            text = t("admin:rooms:list_title", lang) % total

        kb = rooms_list_inline(rooms, locations_map, 0, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "room:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    @router.callback_query(F.data == "room:back")
    async def list_back(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.back_to_reply(
            callback.message,
            admin_rooms(lang),
            title=t("admin:rooms:title", lang),
            menu_context="rooms",
        )
        await callback.answer()

    # ==========================================================
    # VIEW
    # ==========================================================

    @router.callback_query(F.data.startswith("room:view:"))
    async def view_room(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.clear()

        room = await api.get_room(room_id)
        if not room:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        text = await build_room_view_text(room, lang)
        kb = room_view_inline(room, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ==========================================================
    # EDIT (delegation only)
    # ==========================================================

    @router.callback_query(F.data.startswith("room:edit:"))
    async def edit_room(callback: CallbackQuery, state: FSMContext):
        room_id = int(callback.data.split(":")[2])
        await start_room_edit(
            mc=mc,
            callback=callback,
            state=state,
            room_id=room_id,
        )

    # ==========================================================
    # DELETE
    # ==========================================================

    @router.callback_query(F.data.startswith("room:delete:"))
    async def delete_confirm(callback: CallbackQuery):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        room = await api.get_room(room_id)
        if not room:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        text = (
            t("admin:room:confirm_delete", lang) % room["name"]
            + "\n\n"
            + t("admin:room:delete_warning", lang)
        )
        kb = room_delete_confirm_inline(room_id, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("room:delete_confirm:"))
    async def delete_execute(callback: CallbackQuery):
        room_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        ok = await api.delete_room(room_id)
        if not ok:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        await callback.answer(t("admin:room:deleted", lang))

        rooms = await api.get_rooms()
        locations = await api.get_locations()
        locations_map = {loc["id"]: loc["name"] for loc in locations}

        total = len(rooms)

        if total == 0:
            text = f"🚪 {t('admin:rooms:empty', lang)}"
        else:
            text = t("admin:rooms:list_title", lang) % total

        kb = rooms_list_inline(rooms, locations_map, 0, lang)
        await mc.edit_inline(callback.message, text, kb)

    # ==========================================================
    # CREATE
    # ==========================================================

    async def start_create(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        # Проверяем наличие локаций
        locations = await api.get_locations()
        if not locations:
            text = t("admin:room:error_no_locations", lang)
            await mc.show_inline_readonly(message, text, room_cancel_inline(lang))
            return

        # Проверяем наличие услуг
        services = await api.get_services()
        if not services:
            text = t("admin:room:error_no_services", lang)
            await mc.show_inline_readonly(message, text, room_cancel_inline(lang))
            return

        await state.set_state(RoomCreate.location)
        await state.update_data(lang=lang, selected_services=[])

        text = f"{t('admin:room:create_title', lang)}\n\n{t('admin:room:select_location', lang)}"
        await mc.show_inline_input(message, text, locations_select_inline(locations, lang))

    router.start_create = start_create

    # ---- Reply "Back" button во время FSM (escape hatch)
    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomCreate.location)
    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomCreate.name)
    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomCreate.notes)
    @router.message(F.text.in_(t_all("admin:rooms:back")), RoomCreate.services)
    async def fsm_back_escape(message: Message, state: FSMContext):
        """Escape hatch: Reply Back во время FSM → отмена и возврат в меню."""
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        await state.clear()
        await mc.show(
            message,
            admin_rooms(lang),
            title=t("admin:rooms:title", lang),
            menu_context="rooms",
        )

    async def send_step(message: Message, text: str, kb: InlineKeyboardMarkup):
        try:
            await message.delete()
        except Exception:
            pass
        return await mc.send_inline_in_flow(message.bot, message.chat.id, text, kb)

    # ---- location selected
    @router.callback_query(F.data.startswith("room_create:loc:"), RoomCreate.location)
    async def create_location_selected(callback: CallbackQuery, state: FSMContext):
        loc_id = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        location = await api.get_location(loc_id)
        if not location:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        await state.update_data(location_id=loc_id, location_name=location["name"])
        await state.set_state(RoomCreate.name)

        data = await state.get_data()
        text = build_progress_text(data, lang, "admin:room:enter_name")

        await callback.message.edit_text(text, reply_markup=room_cancel_inline(lang))
        await callback.answer()

    # ---- name
    @router.message(RoomCreate.name)
    async def create_name(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        name = message.text.strip()

        if len(name) < 2:
            err = await message.answer(t("admin:room:error_name", lang))
            await mc._add_inline_id(message.chat.id, err.message_id)
            return

        await state.update_data(name=name)
        await state.set_state(RoomCreate.notes)

        data = await state.get_data()
        await send_step(
            message,
            build_progress_text(data, lang, "admin:room:enter_notes"),
            room_skip_inline(lang),
        )

    # ---- notes (skip)
    @router.callback_query(F.data == "room_create:skip", RoomCreate.notes)
    async def skip_notes(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        await state.update_data(notes=None)
        await state.set_state(RoomCreate.services)

        services = await api.get_services()
        data = await state.get_data()
        selected = set(data.get("selected_services", []))

        text = build_progress_text(data, lang, "admin:room:select_services")
        kb = services_multiselect_inline(services, selected, lang)

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    @router.message(RoomCreate.notes)
    async def create_notes(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        await state.update_data(notes=message.text.strip() or None)
        await state.set_state(RoomCreate.services)

        services = await api.get_services()
        data = await state.get_data()
        selected = set(data.get("selected_services", []))

        text = build_progress_text(data, lang, "admin:room:select_services")
        kb = services_multiselect_inline(services, selected, lang)

        await send_step(message, text, kb)

    # ---- services toggle
    @router.callback_query(F.data.startswith("room_create:svc_toggle:"), RoomCreate.services)
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
        text = build_progress_text(data, lang, "admin:room:select_services")
        kb = services_multiselect_inline(services, selected, lang)

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    # ---- services page
    @router.callback_query(F.data.startswith("room_create:svc_page:"), RoomCreate.services)
    async def create_services_page(callback: CallbackQuery, state: FSMContext):
        page = int(callback.data.split(":")[2])
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        data = await state.get_data()
        selected = set(data.get("selected_services", []))

        services = await api.get_services()
        text = build_progress_text(data, lang, "admin:room:select_services")
        kb = services_multiselect_inline(services, selected, lang, page=page)

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data == "room_create:noop")
    async def create_noop(callback: CallbackQuery):
        await callback.answer()

    # ---- services done → CREATE
    @router.callback_query(F.data == "room_create:svc_done", RoomCreate.services)
    async def create_services_done(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()

        selected = set(data.get("selected_services", []))
        if not selected:
            await callback.answer(t("admin:room:error_no_services_selected", lang), show_alert=True)
            return

        # Получаем max display_order для этой локации
        location_id = data["location_id"]
        rooms = await api.get_rooms()
        location_rooms = [r for r in rooms if r["location_id"] == location_id]
        max_order = max((r.get("display_order") or 0 for r in location_rooms), default=0)

        # Создаём комнату
        room = await api.create_room(
            location_id=location_id,
            name=data["name"],
            notes=data.get("notes"),
            display_order=max_order + 1,
        )

        if not room:
            await callback.answer(t("common:error", lang), show_alert=True)
            return

        # Создаём связи с услугами
        for svc_id in selected:
            await api.create_service_room(room["id"], svc_id)

        await state.clear()
        await callback.answer(t("admin:room:created", lang) % data["name"])

        await mc.back_to_reply(
            callback.message,
            admin_rooms(lang),
            title=t("admin:rooms:title", lang),
            menu_context="rooms",
        )

    # ---- cancel create
    @router.callback_query(F.data == "room_create:cancel")
    async def cancel_create(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()
        await callback.answer()
        await mc.back_to_reply(
            callback.message,
            admin_rooms(lang),
            title=t("admin:rooms:title", lang),
            menu_context="rooms",
        )

    # подключаем EDIT router
    router.include_router(setup_edit(mc, get_user_role))

    logger.info("=== rooms router configured ===")
    return router
