"""
bot/app/utils/api.py

HTTP-клиент для запросов через GATEWAY.

Бот → Gateway → Backend

Gateway URL берётся из GATEWAY_URL (не DOMAIN_API_URL!)
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
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.request(method, url, headers=_headers, **kwargs)
                
                if resp.status_code == 204:
                    return None
                    
                if resp.status_code >= 400:
                    logger.error(f"API error: {method} {path} -> {resp.status_code}")
                    return None
                    
                return resp.json()
                
            except Exception as e:
                logger.error(f"API request failed: {method} {path} -> {e}")
                return None

    # ------------------------------------------------------------------
    # Company
    # ------------------------------------------------------------------

    async def get_company(self) -> Optional[dict]:
        """GET /company — первая компания."""
        result = await self._request("GET", "/company")
        if result and len(result) > 0:
            return result[0]
        return None

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------

    async def get_locations(self) -> list[dict]:
        """GET /locations — список активных локаций."""
        result = await self._request("GET", "/locations")
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
        """POST /locations"""
        data = {
            "company_id": company_id,
            "name": name,
            "city": city,
            **kwargs
        }
        return await self._request("POST", "/locations", json=data)

    async def update_location(self, location_id: int, **kwargs) -> Optional[dict]:
        """PATCH /locations/{id}"""
        return await self._request("PATCH", f"/locations/{location_id}", json=kwargs)

    async def delete_location(self, location_id: int) -> bool:
        """DELETE /locations/{id} — soft-delete."""
        result = await self._request("DELETE", f"/locations/{location_id}")
        return result is None


# Singleton
api = ApiClient()
