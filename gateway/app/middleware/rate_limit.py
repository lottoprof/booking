import time
from fastapi import Request, HTTPException
from app.utils.hashing import hash_ua, hash_token
import redis
from app.config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD,
    REDIS_SOCKET_TIMEOUT
)

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    socket_timeout=REDIS_SOCKET_TIMEOUT,
    decode_responses=True
)

def _now() -> int:
    return int(time.time())


def _check_limit(key: str, limit: int, window_sec: int):
    """
    Sliding window counter with Redis TTL
    """
    pipe = redis_client.pipeline()
    pipe.incr(key, 1)
    pipe.ttl(key)
    count, ttl = pipe.execute()

    # первый запрос — ставим TTL
    if ttl == -1:
        redis_client.expire(key, window_sec)

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded"
        )


async def rate_limit_middleware(request: Request, call_next):
    client_type = request.state.client_type
    headers = request.headers

    # -------- PUBLIC (IP + UA) --------
    if client_type == "public":
        ip = headers.get("X-Real-IP") or request.client.host
        ua = headers.get("User-Agent", "")

        ip_key = f"rl:ip:{ip}"
        ua_key = f"rl:ua:{hash_ua(ua)}"

        _check_limit(ip_key, limit=20, window_sec=60)
        _check_limit(ua_key, limit=60, window_sec=60)

    # -------- AUTH CLIENTS (TOKEN) --------
    else:
        token = (
            headers.get("Authorization")
            or headers.get("X-Admin-Token")
            or headers.get("X-Internal-Token")
        )
        token_hash = hash_token(token)
        key = f"rl:token:{token_hash}"

        if client_type == "tg_client":
            _check_limit(key, limit=300, window_sec=60)
        elif client_type == "admin_bot":
            _check_limit(key, limit=600, window_sec=60)
        elif client_type == "internal":
            _check_limit(key, limit=5000, window_sec=60)

    return await call_next(request)

