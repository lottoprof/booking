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


# Singleton
api = ApiClient()

