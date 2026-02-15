"""
bot/app/flows/admin/schedule.py

Объединённый роутер модуля "Расписание".

Подключает:
- schedule_bookings.py — просмотр активных записей
- schedule_overrides.py — изменение расписания
"""

from aiogram import Router

from bot.app.flows.admin import schedule_bookings, schedule_overrides
from bot.app.utils.api import api  # Singleton API client


def setup(menu_controller, get_user_role):
    """
    Настройка роутера расписания.

    Args:
        menu_controller: MenuController instance
        get_user_role: Функция получения роли (для совместимости)

    Returns:
        Router с всеми handlers модуля расписания
    """
    main_router = Router(name="schedule")

    # Инициализируем sub-роутеры
    bookings_router = schedule_bookings.setup(menu_controller, api)
    overrides_router = schedule_overrides.setup(menu_controller, api)

    # Порядок важен: FSM handlers первые
    main_router.include_router(bookings_router)
    main_router.include_router(overrides_router)

    # Экспортируем entry points для context_handlers в admin_reply.py
    main_router.show_bookings = bookings_router.show_bookings
    main_router.show_overrides = overrides_router.show_overrides

    return main_router
