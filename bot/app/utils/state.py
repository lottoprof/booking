"""
Simple in-memory user state.

NOTE:
- state is NOT persistent
- cleared on bot restart
- Redis-based state can be added later
"""

from typing import Dict, Optional


# ----------------------------------------
# User language
# ----------------------------------------

# tg_id -> lang_code (ru / en / ...)
user_lang: Dict[int, str] = {}


def get_user_lang(tg_id: int) -> Optional[str]:
    return user_lang.get(tg_id)


def set_user_lang(tg_id: int, lang: str) -> None:
    user_lang[tg_id] = lang


# ----------------------------------------
# Generic per-user state (optional)
# ----------------------------------------

# tg_id -> state dict
user_state: Dict[int, dict] = {}


def get_state(tg_id: int) -> dict:
    return user_state.setdefault(tg_id, {})


def clear_state(tg_id: int) -> None:
    user_state.pop(tg_id, None)

