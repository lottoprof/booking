# gateway/app/middleware/rate_limit.py
"""
Централизованный rate limiting для gateway.

Лимиты:
- По IP (public clients)
- По UA hash (public clients) 
- По token (authenticated clients)
- По tg_id (webhook requests)
"""

import time
import logging
from typing import Optional

from fastapi import Request, HTTPException

from app.utils.hashing import hash_ua, hash_token
from app.redis_client import redis_client

logger = logging.getLogger(__name__)


# ============================================================
# RATE LIMIT CONFIGURATION
# ============================================================

RATE_LIMITS = {
    # Public clients — по IP и UA
    "public": {
        "ip": {"limit": 20, "window": 60},
        "ua": {"limit": 60, "window": 60},
    },
    
    # Telegram Mini App client
    "tg_client": {
        "token": {"limit": 300, "window": 60},
    },
    
    # Admin bot
    "admin_bot": {
        "token": {"limit": 600, "window": 60},
    },
    
    # Telegram webhook — по tg_id
    # limit=0 означает отключено (для тестов)
    "tg_webhook": {
        "tg_id": {"limit": 0, "window": 60},
    },
}


# ============================================================
# CORE FUNCTIONS
# ============================================================

def _check_limit(key: str, limit: int, window: int) -> tuple[bool, Optional[int]]:
    """
    Проверяет лимит. Возвращает (allowed, retry_after).
    
    limit=0 означает отключено — всегда разрешаем.
    """
    if limit <= 0:
        return True, None
    
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        
        if ttl == -1:
            redis_client.expire(key, window)
            ttl = window
        
        if count > limit:
            return False, ttl
        
        return True, None
        
    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        return True, None  # fail open


def check_rate_limit(
    key_type: str,
    key_value: str,
    client_type: str = "public"
) -> tuple[bool, Optional[int]]:
    """
    Универсальная проверка rate limit.
    
    Args:
        key_type: "ip", "ua", "token", "tg_id"
        key_value: значение для ключа
        client_type: тип клиента для выбора лимитов
    """
    config = RATE_LIMITS.get(client_type, {}).get(key_type)
    if not config:
        return True, None
    
    key = f"rl:{key_type}:{key_value}"
    return _check_limit(key, config["limit"], config["window"])


# ============================================================
# TG WEBHOOK RATE LIMIT
# ============================================================

def check_tg_rate_limit(tg_id: int) -> tuple[bool, Optional[int]]:
    """
    Rate limit для Telegram webhook по tg_id.
    
    Конфигурация в RATE_LIMITS["tg_webhook"]["tg_id"].
    limit=0 — отключено.
    """
    return check_rate_limit("tg_id", str(tg_id), "tg_webhook")


def set_tg_rate_limit(limit: int, window: int = 60):
    """
    Динамическое изменение лимита (для тестов/runtime).
    """
    RATE_LIMITS["tg_webhook"]["tg_id"]["limit"] = limit
    RATE_LIMITS["tg_webhook"]["tg_id"]["window"] = window
    logger.info(f"TG rate limit updated: {limit}/{window}s")


# ============================================================
# MIDDLEWARE
# ============================================================

async def rate_limit_middleware(request: Request, call_next):
    """
    HTTP middleware для rate limiting.
    
    Применяется ко всем запросам кроме internal и webhook.
    Webhook проверяется отдельно в telegram_webhook handler.
    """
    client_type = getattr(request.state, 'client_type', None)
    path = request.url.path
    
    # Internal и webhook — без middleware rate limit
    # (webhook проверяется отдельно по tg_id)
    if client_type == "internal" or path == "/tg/webhook":
        return await call_next(request)
    
    # Неизвестный клиент — public лимиты
    if client_type is None:
        client_type = "public"
    
    headers = request.headers
    
    # PUBLIC: IP + UA
    if client_type == "public":
        ip = headers.get("X-Real-IP") or request.client.host
        ua = headers.get("User-Agent", "")
        
        allowed, retry = check_rate_limit("ip", ip, "public")
        if not allowed:
            raise HTTPException(429, "Rate limit exceeded")
        
        allowed, retry = check_rate_limit("ua", hash_ua(ua), "public")
        if not allowed:
            raise HTTPException(429, "Rate limit exceeded")
    
    # AUTHENTICATED: token
    else:
        token = (
            headers.get("Authorization")
            or headers.get("X-Admin-Token")
            or headers.get("X-Internal-Token")
        )
        if token:
            allowed, retry = check_rate_limit("token", hash_token(token), client_type)
            if not allowed:
                raise HTTPException(429, "Rate limit exceeded")
    
    return await call_next(request)

