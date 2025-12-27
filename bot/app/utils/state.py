"""
bot/app/utils/state.py

User state с Redis persistence.
"""

import os
import redis

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set")

_redis = redis.from_url(REDIS_URL, decode_responses=True)

# TTL для языка — 30 дней
LANG_TTL = 60 * 60 * 24 * 30


# ----------------------------------------
# User language (Redis)
# ----------------------------------------

def get_user_lang(tg_id: int) -> str | None:
    return _redis.get(f"user:lang:{tg_id}")


def set_user_lang(tg_id: int, lang: str) -> None:
    _redis.setex(f"user:lang:{tg_id}", LANG_TTL, lang)


# ----------------------------------------
# Backward compatibility
# ----------------------------------------

class UserLangDict:
    """Dict-like interface для совместимости с user_lang[tg_id]."""
    
    def get(self, tg_id: int, default: str | None = None) -> str | None:
        return get_user_lang(tg_id) or default
    
    def __getitem__(self, tg_id: int) -> str | None:
        return get_user_lang(tg_id)
    
    def __setitem__(self, tg_id: int, lang: str) -> None:
        set_user_lang(tg_id, lang)
    
    def __contains__(self, tg_id: int) -> bool:
        return get_user_lang(tg_id) is not None


user_lang = UserLangDict()

