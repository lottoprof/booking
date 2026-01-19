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

    async def get_users(self, phone: str = None) -> list[dict]:
        """GET /users/ — список активных пользователей."""
        path = "/users/"
        if phone:
            path = f"/users/?phone={phone}"
        result = await self._request("GET", path)
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
        # Telegram может отдать номер без +
        if not phone.startswith('+'):
            phone = '+' + phone
        
        result, status = await self._request_with_status("GET", f"/users/by_phone/{phone}")
        if status == 404:
            return None, False
        if result:
            return result, True
        return None, True  # ошибка (не 404)

    async def create_user(
        self,
        company_id: int,
        phone: str,
        tg_id: int,
        **kwargs
    ) -> Optional[dict]:
        """POST /users/ — создание нового пользователя."""
        # Нормализуем телефон
        if phone and not phone.startswith('+'):
            phone = '+' + phone
    
        data = {
            "company_id": company_id,
            "phone": phone,
            "tg_id": tg_id,
            "first_name": kwargs.get("first_name") or "User",
            **{k: v for k, v in kwargs.items() if k != "first_name"}
        }
        return await self._request("POST", "/users/", json=data)

    async def update_user(self, user_id: int, **kwargs) -> Optional[dict]:
        """PATCH /users/{id} — обновление пользователя."""
        return await self._request("PATCH", f"/users/{user_id}", json=kwargs)

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
                "available_times": [
                    {
                        "time": "10:00",
                        "slot_index": 40,
                        "specialists": [
                            {"id": 5, "name": "Иван Петров"},
                            {"id": 7, "name": "Мария Сидорова"}
                        ]
                    },
                    ...
                ]
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
        status: str = None
    ) -> list[dict]:
        """GET /bookings/ — список записей."""
        params = {}
        if client_id:
            params["client_id"] = client_id
        if status:
            params["status"] = status
        
        result = await self._request("GET", "/bookings/", params=params)
        return result or []

    async def get_booking(self, booking_id: int) -> Optional[dict]:
        """GET /bookings/{id}"""
        return await self._request("GET", f"/bookings/{booking_id}")

    async def create_booking(
        self,
        location_id: int,
        service_id: int,
        specialist_id: int,
        client_id: int,
        datetime_start: str,
        **kwargs
    ) -> Optional[dict]:
        """
        POST /bookings/ — создание записи.
        
        Backend автоматически:
        - Проверяет доступность (Level 2)
        - Назначает room_id
        - Рассчитывает final_price
        
        Returns:
            Booking object или None при конфликте
        """
        data = {
            "location_id": location_id,
            "service_id": service_id,
            "specialist_id": specialist_id,
            "client_id": client_id,
            "datetime": datetime_start,
            **kwargs
        }
        return await self._request("POST", "/bookings/", json=data)

    async def cancel_booking(self, booking_id: int, reason: str = None) -> Optional[dict]:
        """PATCH /bookings/{id} — отмена записи."""
        data = {"status": "cancelled"}
        if reason:
            data["cancel_reason"] = reason
        return await self._request("PATCH", f"/bookings/{booking_id}", json=data)

# Singleton
api = ApiClient()
