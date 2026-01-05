"""
bot/app/utils/api.py

HTTP-клиент для запросов через GATEWAY.

Бот → Gateway → Backend
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Gateway URL — бот ходит ТОЛЬКО через gateway
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")


class ApiClient:
    """Асинхронный клиент для API через gateway."""

    def __init__(self, base_url: str = GATEWAY_URL):
        self.base_url = base_url.rstrip("/")
        logger.info(f"ApiClient initialized with base_url: {self.base_url}")

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict = None,
        **kwargs
    ) -> Optional[dict | list]:
        """Базовый HTTP запрос."""
        url = f"{self.base_url}{path}"
        
        # Bot запросы идут как internal
        _headers = {"X-Internal-Token": os.getenv("INTERNAL_TOKEN", "bot-internal")}
        if headers:
            _headers.update(headers)
        
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            try:
                resp = await client.request(method, url, headers=_headers, **kwargs)
                
                if resp.status_code == 204:
                    return None
                    
                if resp.status_code >= 400:
                    logger.error(f"API error: {method} {path} -> {resp.status_code} {resp.text}")
                    return None
                    
                return resp.json()
                
            except Exception as e:
                logger.error(f"API request failed: {method} {path} -> {e}")
                return None

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


# Singleton
api = ApiClient()
