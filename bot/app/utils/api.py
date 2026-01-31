"""
bot/app/utils/api.py

HTTP-клиент для запросов в Backend напрямую.

Bot — доверенный internal компонент, не нуждается в gateway proxy.
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Backend URL — бот ходит НАПРЯМУЮ в backend (не через gateway)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


class ApiClient:
    """
    Асинхронный клиент для API.
    
    Использует persistent connection pool для эффективности.
    """

    def __init__(self, base_url: str = BACKEND_URL):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        logger.info(f"ApiClient initialized with base_url: {self.base_url}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy initialization of persistent HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=10.0,
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=30.0,
                ),
            )
            logger.info("Created new httpx.AsyncClient")
        return self._client

    async def close(self):
        """Close the HTTP client (call on shutdown)."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("Closed httpx.AsyncClient")

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Optional[dict | list]:
        """Базовый HTTP запрос."""
        client = await self._get_client()
        
        try:
            resp = await client.request(method, path, **kwargs)
            
            if resp.status_code == 204:
                return None
                
            if resp.status_code >= 400:
                logger.error(f"API error: {method} {path} -> {resp.status_code} {resp.text}")
                return None
                
            return resp.json()
            
        except Exception as e:
            logger.error(f"API request failed: {method} {path} -> {e}")
            return None

    async def _request_with_status(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> tuple[Optional[dict | list], int]:
        """HTTP запрос с возвратом статус-кода (для обработки 404)."""
        client = await self._get_client()
        
        try:
            resp = await client.request(method, path, **kwargs)
            
            if resp.status_code == 204:
                return None, 204
                
            if resp.status_code >= 400:
                logger.info(f"API: {method} {path} -> {resp.status_code}")
                return None, resp.status_code
                
            return resp.json(), resp.status_code
            
        except Exception as e:
            logger.error(f"API request failed: {method} {path} -> {e}")
            return None, 0

    # ------------------------------------------------------------------
    # Company
    # ------------------------------------------------------------------

    async def get_company(self) -> Optional[dict]:
        """GET /company/ — первая компания."""
        result = await self._request("GET", "/company/")
        if result and len(result) > 0:
            return result[0]
        return None

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------

    async def get_locations(self) -> list[dict]:
        """GET /locations/ — список активных локаций."""
        result = await self._request("GET", "/locations/")
        return result or []

    async def get_location(self, location_id: int) -> Optional[dict]:
        """GET /locations/{id}"""
        return await self._request("GET", f"/locations/{location_id}")

    async def create_location(
        self,
        company_id: int,
        name: str,
        city: str,
        **kwargs
    ) -> Optional[dict]:
        """POST /locations/"""
        data = {
            "company_id": company_id,
            "name": name,
            "city": city,
            **kwargs
        }
        return await self._request("POST", "/locations/", json=data)

    async def update_location(self, location_id: int, **kwargs) -> Optional[dict]:
        """PATCH /locations/{id}"""
        return await self._request("PATCH", f"/locations/{location_id}", json=kwargs)

    async def delete_location(self, location_id: int) -> bool:
        """DELETE /locations/{id} — soft-delete."""
        result = await self._request("DELETE", f"/locations/{location_id}")
        return result is None

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    async def get_services(self) -> list[dict]:
        """GET /services/ — список активных услуг."""
        result = await self._request("GET", "/services/")
        return result or []

    async def get_service(self, service_id: int) -> Optional[dict]:
        """GET /services/{id}"""
        return await self._request("GET", f"/services/{service_id}")

    async def create_service(
        self,
        company_id: int,
        name: str,
        duration_min: int,
        price: float,
        **kwargs
    ) -> Optional[dict]:
        """POST /services/"""
        data = {
            "company_id": company_id,
            "name": name,
            "duration_min": duration_min,
            "price": price,
            **kwargs
        }
        return await self._request("POST", "/services/", json=data)

    async def update_service(self, service_id: int, **kwargs) -> Optional[dict]:
        """PATCH /services/{id}"""
        return await self._request("PATCH", f"/services/{service_id}", json=kwargs)

    async def delete_service(self, service_id: int) -> bool:
        """DELETE /services/{id} — soft-delete."""
        result = await self._request("DELETE", f"/services/{service_id}")
        return result is None

    # ------------------------------------------------------------------
    # Packages (Service Packages)
    # ------------------------------------------------------------------
    
    async def get_packages(self) -> list[dict]:
        """GET /service_packages/ — список пакетов услуг."""
        result = await self._request("GET", "/service_packages/")
        return result or []
    
    async def get_package(self, package_id: int) -> Optional[dict]:
        """GET /service_packages/{id}"""
        return await self._request("GET", f"/service_packages/{package_id}")
    
    async def create_package(self, data: dict) -> Optional[dict]:
        """POST /service_packages/"""
        return await self._request("POST", "/service_packages/", json=data)
    
    async def patch_package(self, package_id: int, data: dict) -> Optional[dict]:
        """PATCH /service_packages/{id}"""
        return await self._request("PATCH", f"/service_packages/{package_id}", json=data)
    
    async def delete_package(self, package_id: int) -> bool:
        """DELETE /service_packages/{id} — soft-delete."""
        result = await self._request("DELETE", f"/service_packages/{package_id}")
        return result is None

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    async def get_rooms(self) -> list[dict]:
        """GET /rooms/ — список активных комнат."""
        result = await self._request("GET", "/rooms/")
        return result or []

    async def get_room(self, room_id: int) -> Optional[dict]:
        """GET /rooms/{id}"""
        return await self._request("GET", f"/rooms/{room_id}")

    async def create_room(
        self,
        location_id: int,
        name: str,
        **kwargs
    ) -> Optional[dict]:
        """POST /rooms/"""
        data = {
            "location_id": location_id,
            "name": name,
            **kwargs
        }
        return await self._request("POST", "/rooms/", json=data)

    async def update_room(self, room_id: int, **kwargs) -> Optional[dict]:
        """PATCH /rooms/{id}"""
        return await self._request("PATCH", f"/rooms/{room_id}", json=kwargs)

    async def delete_room(self, room_id: int) -> bool:
        """DELETE /rooms/{id} — soft-delete."""
        result = await self._request("DELETE", f"/rooms/{room_id}")
        return result is None

    # ------------------------------------------------------------------
    # Service Rooms (связь комната ↔ услуга)
    # ------------------------------------------------------------------

    async def get_service_rooms(self) -> list[dict]:
        """GET /service_rooms/ — все связи."""
        result = await self._request("GET", "/service_rooms/")
        return result or []

    async def get_service_rooms_by_room(self, room_id: int) -> list[dict]:
        """Получить услуги комнаты (фильтрация на клиенте)."""
        all_sr = await self.get_service_rooms()
        return [sr for sr in all_sr if sr["room_id"] == room_id]

    async def create_service_room(
        self,
        room_id: int,
        service_id: int,
        **kwargs
    ) -> Optional[dict]:
        """POST /service_rooms/"""
        data = {
            "room_id": room_id,
            "service_id": service_id,
            **kwargs
        }
        return await self._request("POST", "/service_rooms/", json=data)

    async def update_service_room(self, sr_id: int, **kwargs) -> Optional[dict]:
        """PATCH /service_rooms/{id}"""
        return await self._request("PATCH", f"/service_rooms/{sr_id}", json=kwargs)

    async def delete_service_room(self, sr_id: int) -> bool:
        """DELETE /service_rooms/{id} — soft-delete."""
        result = await self._request("DELETE", f"/service_rooms/{sr_id}")
        return result is None

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def get_users(self) -> list[dict]:
        """GET /users/ — список активных пользователей."""
        result = await self._request("GET", "/users/")
        return result or []

    async def search_users(self, q: str, limit: int = 20) -> list[dict]:
        """
        GET /users/search — поиск пользователей.
        
        Args:
            q: Search query (min 2 chars)
            limit: Max results (default 20)
        
        Returns:
            List of matching users
        """
        result = await self._request(
            "GET",
            "/users/search",
            params={"q": q, "limit": limit}
        )
        return result or []

    async def get_user(self, user_id: int) -> Optional[dict]:
        """GET /users/{id}"""
        return await self._request("GET", f"/users/{user_id}")

    async def get_user_by_phone(self, phone: str) -> tuple[Optional[dict], bool]:
        """
        GET /users/by_phone/{phone}
        
        Возвращает (user, found):
        - (user_dict, True) — найден
        - (None, False) — не найден (404)
        - (None, True) — ошибка запроса
        """
        if not phone.startswith('+'):
            phone = '+' + phone
        
        result, status = await self._request_with_status("GET", f"/users/by_phone/{phone}")
        if status == 404:
            return None, False
        if result:
            return result, True
        return None, True

    async def get_user_stats(self, user_id: int) -> Optional[dict]:
        """
        GET /users/{id}/stats — статистика записей клиента.
        
        Returns:
            {
                "user_id": 123,
                "total_bookings": 15,
                "active_bookings": 2,
                "completed_bookings": 12,
                "cancelled_bookings": 1
            }
        """
        return await self._request("GET", f"/users/{user_id}/stats")

    async def change_user_role(self, user_id: int, role: str) -> Optional[dict]:
        """
        PATCH /users/{id}/role — смена роли пользователя.
        
        Args:
            user_id: User ID
            role: New role ("client", "specialist", "manager")
        
        Returns:
            {
                "user_id": 123,
                "old_role": "client",
                "new_role": "specialist"
            }
        """
        return await self._request(
            "PATCH",
            f"/users/{user_id}/role",
            json={"role": role}
        )

    async def create_user(
        self,
        company_id: int,
        first_name: str,
        phone: str = None,
        tg_id: int = None,
        **kwargs
    ) -> Optional[dict]:
        """POST /users/ — создание нового пользователя."""
        if phone and not phone.startswith('+'):
            phone = '+' + phone
    
        data = {
            "company_id": company_id,
            "first_name": first_name,
            **kwargs
        }
        if phone:
            data["phone"] = phone
        if tg_id:
            data["tg_id"] = tg_id
            
        return await self._request("POST", "/users/", json=data)

    async def update_user(self, user_id: int, **kwargs) -> Optional[dict]:
        """PATCH /users/{id} — обновление пользователя."""
        return await self._request("PATCH", f"/users/{user_id}", json=kwargs)

    async def delete_user(self, user_id: int) -> bool:
        """DELETE /users/{id} — soft-delete (деактивация)."""
        result = await self._request("DELETE", f"/users/{user_id}")
        return result is None

    # ------------------------------------------------------------------
    # User Roles
    # ------------------------------------------------------------------

    async def create_user_role(self, user_id: int, role_id: int) -> Optional[dict]:
        """POST /user_roles/ — назначение роли пользователю."""
        data = {
            "user_id": user_id,
            "role_id": role_id,
        }
        return await self._request("POST", "/user_roles/", json=data)

    # ------------------------------------------------------------------
    # Specialists
    # ------------------------------------------------------------------

    async def get_specialists(self) -> list[dict]:
        """GET /specialists/ — список активных специалистов."""
        result = await self._request("GET", "/specialists/")
        return result or []

    async def get_specialist(self, specialist_id: int) -> Optional[dict]:
        """GET /specialists/{id}"""
        return await self._request("GET", f"/specialists/{specialist_id}")

    async def create_specialist(
        self,
        user_id: int,
        **kwargs
    ) -> Optional[dict]:
        """POST /specialists/"""
        data = {
            "user_id": user_id,
            **kwargs
        }
        return await self._request("POST", "/specialists/", json=data)

    async def update_specialist(self, specialist_id: int, **kwargs) -> Optional[dict]:
        """PATCH /specialists/{id}"""
        return await self._request("PATCH", f"/specialists/{specialist_id}", json=kwargs)

    async def delete_specialist(self, specialist_id: int) -> bool:
        """DELETE /specialists/{id} — soft-delete."""
        result = await self._request("DELETE", f"/specialists/{specialist_id}")
        return result is None

    # ------------------------------------------------------------------
    # Specialist Services (связь специалист ↔ услуга)
    # ------------------------------------------------------------------

    async def get_specialist_services(self, specialist_id: int) -> list[dict]:
        """GET /specialists/{id}/services — услуги специалиста."""
        result = await self._request("GET", f"/specialists/{specialist_id}/services")
        return result or []

    async def add_specialist_service(
        self,
        specialist_id: int,
        service_id: int,
        **kwargs
    ) -> Optional[dict]:
        """POST /specialists/{id}/services"""
        data = {
            "service_id": service_id,
            **kwargs
        }
        return await self._request("POST", f"/specialists/{specialist_id}/services", json=data)

    async def update_specialist_service(
        self,
        specialist_id: int,
        service_id: int,
        **kwargs
    ) -> Optional[dict]:
        """PATCH /specialists/{id}/services/{service_id}"""
        return await self._request(
            "PATCH",
            f"/specialists/{specialist_id}/services/{service_id}",
            json=kwargs
        )

    async def delete_specialist_service(
        self,
        specialist_id: int,
        service_id: int
    ) -> bool:
        """DELETE /specialists/{id}/services/{service_id} — soft-delete."""
        result = await self._request(
            "DELETE",
            f"/specialists/{specialist_id}/services/{service_id}"
        )
        return result is None

    # ------------------------------------------------------------------
    # Slots (Level 1 + Level 2)
    # ------------------------------------------------------------------

    async def get_slots_calendar(
        self,
        location_id: int,
        start_date: str = None,
        end_date: str = None
    ) -> Optional[dict]:
        """
        GET /slots/calendar — Level 1: базовая сетка локации.
        
        Returns:
            {
                "location_id": 1,
                "start_date": "2026-01-20",
                "end_date": "2026-03-20",
                "days": [
                    {"date": "2026-01-20", "has_slots": true, "open_slots_count": 36},
                    ...
                ],
                "horizon_days": 60,
                "min_advance_hours": 6
            }
        """
        params = {"location_id": location_id}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        return await self._request("GET", "/slots/calendar", params=params)

    async def get_slots_day(
        self,
        location_id: int,
        service_id: int,
        date: str
    ) -> Optional[dict]:
        """
        GET /slots/day — Level 2: гранулярный расчёт для услуги.
        
        Returns:
            {
                "location_id": 1,
                "service_id": 12,
                "date": "2026-01-20",
                "service_duration_min": 60,
                "slots_needed": 4,
                "available_times": [...]
            }
        """
        params = {
            "location_id": location_id,
            "service_id": service_id,
            "date": date
        }
        return await self._request("GET", "/slots/day", params=params)

    # ------------------------------------------------------------------
    # Bookings
    # ------------------------------------------------------------------

    async def get_bookings(
        self,
        client_id: int = None,
        location_id: int = None,
        specialist_id: int = None,
        status: str = None,
        date: str = None,
        date_from: str = None,
        date_to: str = None,
    ) -> list[dict]:
        """
        GET /bookings/ — список записей с фильтрами.
        
        Args:
            client_id: Filter by client
            location_id: Filter by location
            specialist_id: Filter by specialist
            status: Filter by status (pending, confirmed, cancelled, done)
            date: Filter by exact date (YYYY-MM-DD)
            date_from: Filter date_start >= date_from
            date_to: Filter date_start <= date_to
        """
        params = {}
        if client_id:
            params["client_id"] = client_id
        if location_id:
            params["location_id"] = location_id
        if specialist_id:
            params["specialist_id"] = specialist_id
        if status:
            params["status"] = status
        if date:
            params["date"] = date
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        
        result = await self._request("GET", "/bookings/", params=params)
        return result or []

    async def get_booking(self, booking_id: int) -> Optional[dict]:
        """GET /bookings/{id}"""
        return await self._request("GET", f"/bookings/{booking_id}")

    async def create_booking(
        self,
        company_id: int,
        location_id: int,
        service_id: int,
        specialist_id: int,
        client_id: int,
        date_start: str,
        date_end: str,
        duration_minutes: int,
        break_minutes: int = 0,
        room_id: int = None,
        notes: str = None,
        initiated_by_user_id: int = None,
        initiated_by_role: str = None,
        initiated_by_channel: str = None,
    ) -> Optional[dict]:
        """
        POST /bookings/ — создание записи.

        Args:
            company_id: Company ID (required)
            location_id: Location ID (required)
            service_id: Service ID (required)
            specialist_id: Specialist ID (required)
            client_id: Client user ID (required)
            date_start: Start datetime ISO format (required)
            date_end: End datetime ISO format (required)
            duration_minutes: Duration in minutes (required)
            break_minutes: Break after service (default 0)
            room_id: Room ID (optional)
            notes: Notes (optional)
            initiated_by_user_id: User who initiated the action (optional)
            initiated_by_role: Role of initiator (optional)
            initiated_by_channel: Channel: tg_bot, web, api (optional)

        Returns:
            Booking object или None при ошибке
        """
        data = {
            "company_id": company_id,
            "location_id": location_id,
            "service_id": service_id,
            "specialist_id": specialist_id,
            "client_id": client_id,
            "date_start": date_start,
            "date_end": date_end,
            "duration_minutes": duration_minutes,
            "break_minutes": break_minutes,
        }
        if room_id:
            data["room_id"] = room_id
        if notes:
            data["notes"] = notes

        headers = {}
        if initiated_by_user_id:
            headers["X-Initiated-By-User-Id"] = str(initiated_by_user_id)
        if initiated_by_role:
            headers["X-Initiated-By-Role"] = initiated_by_role
        if initiated_by_channel:
            headers["X-Initiated-By-Channel"] = initiated_by_channel

        return await self._request(
            "POST", "/bookings/", json=data, headers=headers
        )

    async def update_booking(
        self,
        booking_id: int,
        initiated_by_user_id: int = None,
        initiated_by_role: str = None,
        initiated_by_channel: str = None,
        **kwargs,
    ) -> Optional[dict]:
        """
        PATCH /bookings/{id} — обновление записи (admin).

        Допустимые поля:
            - date_start, date_end: Перенос записи
            - specialist_id: Смена специалиста
            - service_id: Смена услуги
            - duration_minutes: Изменение длительности
            - final_price: Изменение цены
            - room_id: Смена комнаты
            - status: Изменение статуса
            - cancel_reason: Причина отмены
            - notes: Заметки
        """
        headers = {}
        if initiated_by_user_id:
            headers["X-Initiated-By-User-Id"] = str(initiated_by_user_id)
        if initiated_by_role:
            headers["X-Initiated-By-Role"] = initiated_by_role
        if initiated_by_channel:
            headers["X-Initiated-By-Channel"] = initiated_by_channel

        return await self._request(
            "PATCH", f"/bookings/{booking_id}", json=kwargs, headers=headers
        )

    async def cancel_booking(
        self,
        booking_id: int,
        reason: str = None,
        initiated_by_user_id: int = None,
        initiated_by_role: str = None,
        initiated_by_channel: str = None,
    ) -> Optional[dict]:
        """PATCH /bookings/{id} — отмена записи."""
        data = {"status": "cancelled"}
        if reason:
            data["cancel_reason"] = reason

        headers = {}
        if initiated_by_user_id:
            headers["X-Initiated-By-User-Id"] = str(initiated_by_user_id)
        if initiated_by_role:
            headers["X-Initiated-By-Role"] = initiated_by_role
        if initiated_by_channel:
            headers["X-Initiated-By-Channel"] = initiated_by_channel

        return await self._request(
            "PATCH", f"/bookings/{booking_id}", json=data, headers=headers
        )

    async def confirm_booking(self, booking_id: int) -> Optional[dict]:
        """PATCH /bookings/{id} — подтверждение записи."""
        return await self._request(
            "PATCH",
            f"/bookings/{booking_id}",
            json={"status": "confirmed"}
        )

    async def complete_booking(self, booking_id: int) -> Optional[dict]:
        """PATCH /bookings/{id} — завершение записи."""
        return await self._request(
            "PATCH",
            f"/bookings/{booking_id}",
            json={"status": "done"}
        )

    # ------------------------------------------------------------------
    # Wallets (Domain API)
    # ------------------------------------------------------------------

    async def get_wallet(self, user_id: int) -> Optional[dict]:
        """
        GET /wallets/{user_id} — получить кошелёк.
        Создаёт автоматически если не существует.
        """
        return await self._request("GET", f"/wallets/{user_id}")

    async def get_wallet_transactions(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list[dict]:
        """
        GET /wallets/{user_id}/transactions — история операций.
        """
        result = await self._request(
            "GET",
            f"/wallets/{user_id}/transactions",
            params={"limit": limit, "offset": offset}
        )
        return result or []

    async def wallet_deposit(
        self,
        user_id: int,
        amount: float,
        description: str = None,
        created_by: int = None,
    ) -> Optional[dict]:
        """
        POST /wallets/{user_id}/deposit — пополнение кошелька.
        
        Returns:
            {
                "success": true,
                "wallet_id": 1,
                "new_balance": 1500.0,
                "transaction_id": 42,
                "message": "Deposited 500.00 RUB"
            }
        """
        data = {"amount": amount}
        if description:
            data["description"] = description
        if created_by:
            data["created_by"] = created_by
        return await self._request("POST", f"/wallets/{user_id}/deposit", json=data)

    async def wallet_withdraw(
        self,
        user_id: int,
        amount: float,
        description: str = None,
        created_by: int = None,
    ) -> Optional[dict]:
        """
        POST /wallets/{user_id}/withdraw — списание средств.
        
        Возвращает None при недостаточном балансе (400).
        """
        data = {"amount": amount}
        if description:
            data["description"] = description
        if created_by:
            data["created_by"] = created_by
        return await self._request("POST", f"/wallets/{user_id}/withdraw", json=data)

    async def wallet_payment(
        self,
        user_id: int,
        amount: float,
        booking_id: int,
        description: str = None,
    ) -> Optional[dict]:
        """
        POST /wallets/{user_id}/payment — оплата записи.
        
        Возвращает None при недостаточном балансе или несуществующей записи.
        """
        data = {
            "amount": amount,
            "booking_id": booking_id,
        }
        if description:
            data["description"] = description
        return await self._request("POST", f"/wallets/{user_id}/payment", json=data)

    async def wallet_refund(
        self,
        user_id: int,
        amount: float,
        booking_id: int = None,
        description: str = None,
        created_by: int = None,
    ) -> Optional[dict]:
        """
        POST /wallets/{user_id}/refund — возврат средств.
        """
        data = {"amount": amount}
        if booking_id:
            data["booking_id"] = booking_id
        if description:
            data["description"] = description
        if created_by:
            data["created_by"] = created_by
        return await self._request("POST", f"/wallets/{user_id}/refund", json=data)

    async def wallet_correction(
        self,
        user_id: int,
        amount: float,
        description: str,
        created_by: int,
    ) -> Optional[dict]:
        """
        POST /wallets/{user_id}/correction — корректировка баланса (admin).
        
        Args:
            amount: Может быть + или -
            description: Причина (обязательно, мин. 3 символа)
            created_by: ID админа (обязательно)
        """
        data = {
            "amount": amount,
            "description": description,
            "created_by": created_by,
        }
        return await self._request("POST", f"/wallets/{user_id}/correction", json=data)

    # ------------------------------------------------------------------
    # Users (Clients module)
    # ------------------------------------------------------------------

    async def get_user(self, user_id: int) -> Optional[dict]:
        """GET /users/{id}"""
        return await self._request("GET", f"/users/{user_id}")

    async def update_user(self, user_id: int, **kwargs) -> Optional[dict]:
        """PATCH /users/{id}"""
        return await self._request("PATCH", f"/users/{user_id}", json=kwargs)

    async def delete_user(self, user_id: int) -> bool:
        """DELETE /users/{id} — soft-delete (is_active=0)."""
        result = await self._request("DELETE", f"/users/{user_id}")
        return result is None

    async def search_users(self, query: str, limit: int = 20) -> list[dict]:
        """
        GET /users/search?q=...
        
        Search by phone, first_name, or last_name.
        Min query length: 2 chars.
        """
        result = await self._request(
            "GET",
            "/users/search",
            params={"q": query, "limit": limit}
        )
        return result or []

    async def get_user_stats(self, user_id: int) -> Optional[dict]:
        """
        GET /users/{id}/stats
        
        Returns:
            {
                "user_id": 1,
                "total_bookings": 10,
                "active_bookings": 2,
                "completed_bookings": 7,
                "cancelled_bookings": 1
            }
        """
        return await self._request("GET", f"/users/{user_id}/stats")

    async def get_user_active_bookings(self, user_id: int) -> list[dict]:
        """
        GET /users/{id}/active-bookings
        
        Returns bookings with status 'pending' or 'confirmed'.
        Used before deactivation to show upcoming appointments.
        """
        result = await self._request("GET", f"/users/{user_id}/active-bookings")
        return result or []

    async def change_user_role(self, user_id: int, new_role: str) -> Optional[dict]:
        """
        PATCH /users/{id}/role
        
        Args:
            user_id: User ID
            new_role: "client" | "specialist" | "manager" | "admin"
        
        Returns:
            {
                "user_id": 1,
                "old_role": "client",
                "new_role": "specialist"
            }
        """
        return await self._request(
            "PATCH",
            f"/users/{user_id}/role",
            json={"role": new_role}
        )

    # ------------------------------------------------------------------
    # User Roles (for reading only, changes via /users/{id}/role)
    # ------------------------------------------------------------------

    async def get_user_roles(self, user_id: int) -> list[dict]:
        """
        GET /user_roles/ filtered by user_id.
        
        Returns role records for user.
        """
        all_roles = await self._request("GET", "/user_roles/")
        if not all_roles:
            return []
        return [r for r in all_roles if r.get("user_id") == user_id]

    # ------------------------------------------------------------------
    # Notification Settings
    # ------------------------------------------------------------------

    async def get_notification_settings(
        self,
        company_id: int = None,
        event_type: str = None,
        recipient_role: str = None,
    ) -> list[dict]:
        """GET /notification_settings/ with optional filters."""
        params = {}
        if company_id:
            params["company_id"] = company_id
        if event_type:
            params["event_type"] = event_type
        if recipient_role:
            params["recipient_role"] = recipient_role
        result = await self._request("GET", "/notification_settings/", params=params)
        return result or []

    # ------------------------------------------------------------------
    # Ad Templates
    # ------------------------------------------------------------------

    async def get_ad_template(self, template_id: int) -> Optional[dict]:
        """GET /ad_templates/{id}"""
        return await self._request("GET", f"/ad_templates/{template_id}")

    # ------------------------------------------------------------------
    # Users by role (for notification recipients)
    # ------------------------------------------------------------------

    async def get_users_by_role(self, role_name: str) -> list[dict]:
        """
        Get users that have a specific role.

        Fetches all user_roles, filters by role, then fetches user details.
        """
        all_roles = await self._request("GET", "/user_roles/")
        if not all_roles:
            return []

        # Roles table: admin=1, specialist=2, manager=3, client=4
        role_map = {"admin": 1, "specialist": 2, "manager": 3, "client": 4}
        role_id = role_map.get(role_name)
        if not role_id:
            return []

        user_ids = list({
            r["user_id"] for r in all_roles if r.get("role_id") == role_id
        })

        users = []
        for uid in user_ids:
            user = await self.get_user(uid)
            if user and user.get("is_active", 0):
                users.append(user)

        return users

    async def get_push_subscriptions_by_user(self, user_id: int) -> list[dict]:
        """Get push subscriptions for a user."""
        all_subs = await self._request("GET", "/push_subscriptions/")
        if not all_subs:
            return []
        return [s for s in all_subs if s.get("user_id") == user_id]

    # ------------------------------------------------------------------
    # Client Packages (purchased packages)
    # ------------------------------------------------------------------

    async def get_user_packages(self, user_id: int, include_closed: bool = False) -> list[dict]:
        """
        GET /client_packages/user/{user_id} — packages purchased by user.

        Returns packages with remaining service counts.
        By default excludes closed packages.
        """
        params = {}
        if include_closed:
            params["include_closed"] = "true"
        result = await self._request("GET", f"/client_packages/user/{user_id}", params=params)
        return result or []


# Singleton
api = ApiClient()

