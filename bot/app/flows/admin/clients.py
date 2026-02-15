"""
bot/app/flows/admin/clients.py

Объединённый роутер модуля "Клиенты".

Подключает:
- clients_find.py — поиск + карточка + деактивация
- clients_edit.py — редактирование полей
- clients_wallets.py — операции с кошельком
- clients_sell_package.py — продажа пакета клиенту
- clients_booking.py — запись от имени клиента
"""

from aiogram import Router

from bot.app.flows.admin import (
    clients_booking,
    clients_bookings_list,
    clients_edit,
    clients_find,
    clients_sell_package,
    clients_wallets,
)
from bot.app.utils.api import api  # Singleton API client


def setup(menu_controller, get_user_role):
    """
    Настройка роутера клиентов.

    Args:
        menu_controller: MenuController instance
        get_user_role: Функция получения роли (для совместимости)

    Returns:
        Router с всеми handlers модуля клиентов
    """
    main_router = Router(name="clients")

    # Инициализируем sub-роутеры (передаём api singleton)
    find_router = clients_find.setup(menu_controller, api)
    edit_router = clients_edit.setup(menu_controller, api)
    wallets_router = clients_wallets.setup(menu_controller, api)
    sell_package_router = clients_sell_package.setup(menu_controller, api)
    booking_router = clients_booking.setup(menu_controller, api)
    bookings_list_router = clients_bookings_list.setup(menu_controller, api)

    # Связываем роутеры для делегирования
    find_router.edit_router = edit_router
    find_router.wallets_router = wallets_router

    # Порядок важен: FSM handlers первые
    main_router.include_router(find_router)
    main_router.include_router(edit_router)
    main_router.include_router(wallets_router)
    main_router.include_router(sell_package_router)
    main_router.include_router(booking_router)
    main_router.include_router(bookings_list_router)

    # Экспортируем start_search и show_bookings_list для context_handlers
    main_router.start_search = find_router.start_search
    main_router.show_bookings_list = bookings_list_router.show_bookings_list

    return main_router

