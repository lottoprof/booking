"""
bot/app/flows/admin/clients.py

Объединённый роутер модуля "Клиенты".

Подключает:
- clients_find.py — поиск + карточка + деактивация
- clients_edit.py — редактирование полей
- clients_wallets.py — операции с кошельком
"""

from aiogram import Router

from bot.app.flows.admin import clients_find
from bot.app.flows.admin import clients_edit
from bot.app.flows.admin import clients_wallets
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
    
    # Связываем роутеры для делегирования
    find_router.edit_router = edit_router
    find_router.wallets_router = wallets_router
    
    # Порядок важен: FSM handlers первые
    main_router.include_router(find_router)
    main_router.include_router(edit_router)
    main_router.include_router(wallets_router)
    
    # Экспортируем start_search для context_handlers
    main_router.start_search = find_router.start_search
    
    return main_router

