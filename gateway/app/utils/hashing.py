# Для rate-limit (UA, token).

import hashlib

def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def hash_ua(user_agent: str | None) -> str:
    if not user_agent:
        return "no-ua"
    return hash_value(user_agent)

def hash_token(token: str | None) -> str:
    if not token:
        return "no-token"
    return hash_value(token)

