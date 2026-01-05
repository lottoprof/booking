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
    key = _cache_key(tg_id)
    try:
        data = redis_client.get(key)
        logger.info(f"[CACHE] GET {key} -> {'HIT' if data else 'MISS'}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"[CACHE] GET error: {e}")
    return None


def _set_cached_user(tg_id: int, user_data: dict):
    """Сохраняет данные пользователя в кэш."""
    key = _cache_key(tg_id)
    try:
        value = json.dumps(user_data)
        result = redis_client.setex(key, USER_CACHE_TTL, value)
        logger.info(f"[CACHE] SET {key} -> {result}, TTL={USER_CACHE_TTL}")
    except Exception as e:
        logger.error(f"[CACHE] SET error: {e}")


def invalidate_user_cache(tg_id: int):
    """Инвалидирует кэш пользователя. Вызывается после регистрации."""
    key = _cache_key(tg_id)
    try:
        redis_client.delete(key)
        logger.info(f"[CACHE] DELETE {key}")
    except Exception as e:
        logger.error(f"[CACHE] DELETE error: {e}")


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
# BACKEND: fetch user (without create)
# ============================================================

async def _fetch_user_from_backend(tg_id: int) -> Optional[dict]:
    """
    Ищет пользователя по tg_id в backend.
    
    Возвращает dict с user_id, company_id, role, is_new=False если найден.
    Возвращает None если не найден или БД недоступна.
    
    НЕ создаёт пользователя — создание происходит в Bot после запроса телефона.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
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
            elif resp.status_code == 404:
                # Пользователь не найден — это нормально, требуется регистрация
                logger.info(f"[AUTH] User not found by tg_id={tg_id}, registration required")
                return None
            else:
                logger.error(f"[AUTH] Unexpected status: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"User lookup failed: {e}")
            return None


# ============================================================
# MAIN: authenticate_tg_user
# ============================================================

async def authenticate_tg_user(update: dict) -> Optional[TgUserContext]:
    """
    Главная функция аутентификации.
    
    1. Извлекает tg_id из update
    2. Проверяет кэш Redis (TTL 10 мин)
    3. Если нет в кэше — запрос к backend (только поиск, без создания)
    4. Кэширует результат если найден
    
    Возвращает TgUserContext:
    - user_id заполнен, is_new=False — пользователь найден
    - user_id=None, is_new=True — требуется регистрация (запрос телефона)
    
    Возвращает None только если нет tg_id в update.
    """
    tg_id = extract_tg_id(update)
    if not tg_id:
        logger.warning("No tg_id in update")
        return None
    
    logger.info(f"[AUTH] authenticate_tg_user called for tg_id={tg_id}")
    
    # 1. Проверяем кэш
    cached = _get_cached_user(tg_id)
    if cached:
        logger.info(f"[AUTH] Cache hit for tg_id={tg_id}, role={cached.get('role')}")
        return TgUserContext(
            tg_id=tg_id,
            user_id=cached["user_id"],
            company_id=cached["company_id"],
            role=cached["role"],
            is_new=False,
        )
    
    logger.info(f"[AUTH] Cache miss, fetching from backend...")
    
    # 2. Запрос к backend (только поиск)
    user_data = await _fetch_user_from_backend(tg_id)
    
    if user_data:
        # Пользователь найден — кэшируем
        cache_data = {
            "user_id": user_data["user_id"],
            "company_id": user_data["company_id"],
            "role": user_data["role"],
        }
        _set_cached_user(tg_id, cache_data)
        
        logger.info(f"[AUTH] User found: tg_id={tg_id}, role={user_data['role']}")
        
        return TgUserContext(
            tg_id=tg_id,
            user_id=user_data["user_id"],
            company_id=user_data["company_id"],
            role=user_data["role"],
            is_new=False,
        )
    
    # 3. Пользователь не найден — требуется регистрация
    logger.info(f"[AUTH] User not found, registration required: tg_id={tg_id}")
    
    return TgUserContext(
        tg_id=tg_id,
        user_id=None,
        company_id=None,
        role="client",  # дефолтная роль для нового
        is_new=True,
    )
