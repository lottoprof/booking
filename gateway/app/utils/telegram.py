# gateway/app/utils/telegram.py
"""
Telegram utilities для gateway.

Содержит:
- verify_init_data() — проверка подписи Mini App initData
- extract_tg_id() — извлечение tg_id из webhook update
- authenticate_tg_user() — аутентификация пользователя (с кэшем Redis)
"""

import hmac
import hashlib
import time
import json
import logging
from urllib.parse import parse_qsl
from typing import Dict, Optional
from dataclasses import dataclass

import httpx

from app.config import DOMAIN_API_URL
from app.redis_client import redis_client

logger = logging.getLogger(__name__)

# Cache TTL — 10 минут
USER_CACHE_TTL = 600


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class TgUserContext:
    """Контекст пользователя для передачи в bot."""
    tg_id: int
    user_id: Optional[int]
    company_id: Optional[int]
    role: str
    is_new: bool


# ============================================================
# MINI APP: initData verification
# ============================================================

def verify_init_data(init_data: str, bot_token: str, ttl_sec: int = 86400) -> Dict:
    """
    Проверка подписи Telegram initData + TTL.
    Используется для Mini App авторизации.
    """
    data = dict(parse_qsl(init_data, strict_parsing=True))

    if "hash" not in data:
        raise ValueError("Missing hash")

    received_hash = data.pop("hash")

    auth_date = int(data.get("auth_date", "0"))
    if auth_date == 0 or time.time() - auth_date > ttl_sec:
        raise ValueError("initData expired")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items())
    )

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid initData signature")

    return data


# ============================================================
# WEBHOOK: extract from update
# ============================================================

def extract_tg_id(update: dict) -> Optional[int]:
    """Извлекает tg_id из Telegram webhook update."""
    sources = [
        ("message", "from"),
        ("callback_query", "from"),
        ("inline_query", "from"),
        ("edited_message", "from"),
        ("chosen_inline_result", "from"),
        ("shipping_query", "from"),
        ("pre_checkout_query", "from"),
    ]
    
    for key, nested in sources:
        if key in update:
            user = update[key].get(nested, {})
            if user and "id" in user:
                return user["id"]
    
    return None


def extract_user_info(update: dict) -> dict:
    """Извлекает информацию о пользователе из update."""
    sources = ["message", "callback_query", "inline_query", "edited_message"]
    
    for key in sources:
        if key in update:
            user = update[key].get("from", {})
            if user:
                return {
                    "tg_id": user.get("id"),
                    "tg_username": user.get("username"),
                    "first_name": user.get("first_name"),
                    "last_name": user.get("last_name"),
                }
    
    return {}


# ============================================================
# CACHE: Redis
# ============================================================

def _cache_key(tg_id: int) -> str:
    return f"tg_user:{tg_id}"


def _get_cached_user(tg_id: int) -> Optional[dict]:
    """Получает данные пользователя из кэша."""
    try:
        data = redis_client.get(_cache_key(tg_id))
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None


def _set_cached_user(tg_id: int, user_data: dict):
    """Сохраняет данные пользователя в кэш."""
    try:
        redis_client.setex(
            _cache_key(tg_id),
            USER_CACHE_TTL,
            json.dumps(user_data)
        )
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


# ============================================================
# BACKEND: get company_id
# ============================================================

async def _get_company_id() -> Optional[int]:
    """
    Получает company_id из БД.
    Возвращает None если компания не найдена — это ошибка конфигурации.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{DOMAIN_API_URL}/company/")
            if resp.status_code == 200:
                companies = resp.json()
                if companies:
                    return companies[0]["id"]
        except Exception as e:
            logger.error(f"Get company failed: {e}")
    
    return None


# ============================================================
# BACKEND: get user role
# ============================================================

async def _get_user_role(user_id: int) -> str:
    """Получает роль пользователя. Приоритет: admin > manager > specialist > client"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{DOMAIN_API_URL}/user_roles/")
            if resp.status_code != 200:
                return "client"
            
            user_roles = [ur for ur in resp.json() if ur["user_id"] == user_id]
            if not user_roles:
                return "client"
            
            resp = await client.get(f"{DOMAIN_API_URL}/roles/")
            if resp.status_code != 200:
                return "client"
            
            roles_map = {r["id"]: r["name"] for r in resp.json()}
            priority = ["admin", "manager", "specialist", "client"]
            user_role_names = [roles_map.get(ur["role_id"], "client") for ur in user_roles]
            
            for role in priority:
                if role in user_role_names:
                    return role
            
            return "client"
            
        except Exception as e:
            logger.warning(f"Get role failed: {e}")
            return "client"


# ============================================================
# BACKEND: fetch or create user
# ============================================================

async def _fetch_user_from_backend(tg_id: int, user_info: dict) -> Optional[dict]:
    """
    Получает или создаёт пользователя в backend.
    Возвращает dict с user_id, company_id, role, is_new.
    Возвращает None при ошибке — пользователь НЕ создаётся если БД недоступна.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Ищем существующего пользователя
        try:
            resp = await client.get(f"{DOMAIN_API_URL}/users/by_tg/{tg_id}")
            if resp.status_code == 200:
                user = resp.json()
                role = await _get_user_role(user["id"])
                return {
                    "user_id": user["id"],
                    "company_id": user["company_id"],
                    "role": role,
                    "is_new": False,
                }
        except Exception as e:
            logger.error(f"User lookup failed: {e}")
            return None  # БД недоступна — не продолжаем
        
        # 2. Пользователь не найден — создаём нового
        # Сначала получаем company_id
        company_id = await _get_company_id()
        if not company_id:
            logger.error("Cannot create user: no company in database")
            return None
        
        try:
            create_data = {
                "company_id": company_id,
                "first_name": user_info.get("first_name") or "User",
                "last_name": user_info.get("last_name"),
                "tg_id": tg_id,
                "tg_username": user_info.get("tg_username"),
            }
            resp = await client.post(f"{DOMAIN_API_URL}/users/", json=create_data)
            
            if resp.status_code == 201:
                user = resp.json()
                logger.info(f"Created user: tg_id={tg_id}, user_id={user['id']}")
                
                # Назначаем роль client
                await client.post(
                    f"{DOMAIN_API_URL}/user_roles/",
                    json={"user_id": user["id"], "role_id": 4}
                )
                
                return {
                    "user_id": user["id"],
                    "company_id": company_id,
                    "role": "client",
                    "is_new": True,
                }
            else:
                logger.error(f"Create user failed: {resp.status_code} {resp.text}")
                
        except Exception as e:
            logger.error(f"Create user error: {e}")
        
        return None


# ============================================================
# MAIN: authenticate_tg_user
# ============================================================

async def authenticate_tg_user(update: dict) -> Optional[TgUserContext]:
    """
    Главная функция аутентификации.
    
    1. Извлекает tg_id из update
    2. Проверяет кэш Redis (TTL 10 мин)
    3. Если нет — запрос к backend (get or create)
    4. Кэширует результат
    
    Возвращает None если:
    - Нет tg_id в update
    - БД недоступна
    - Нет компании в БД (bootstrap не выполнен)
    """
    tg_id = extract_tg_id(update)
    if not tg_id:
        logger.warning("No tg_id in update")
        return None
    
    # 1. Проверяем кэш
    cached = _get_cached_user(tg_id)
    if cached:
        return TgUserContext(
            tg_id=tg_id,
            user_id=cached["user_id"],
            company_id=cached["company_id"],
            role=cached["role"],
            is_new=False,
        )
    
    # 2. Запрос к backend
    user_info = extract_user_info(update)
    user_data = await _fetch_user_from_backend(tg_id, user_info)
    
    if not user_data:
        return None
    
    # 3. Кэшируем
    _set_cached_user(tg_id, {
        "user_id": user_data["user_id"],
        "company_id": user_data["company_id"],
        "role": user_data["role"],
    })
    
    return TgUserContext(
        tg_id=tg_id,
        user_id=user_data["user_id"],
        company_id=user_data["company_id"],
        role=user_data["role"],
        is_new=user_data["is_new"],
    )

