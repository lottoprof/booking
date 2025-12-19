import hmac
import hashlib
import time
from urllib.parse import parse_qsl
from typing import Dict


def verify_init_data(init_data: str, bot_token: str, ttl_sec: int = 86400) -> Dict:
    """
    Проверка подписи Telegram initData + TTL.
    Возвращает распарсенные данные или кидает ValueError.
    """

    data = dict(parse_qsl(init_data, strict_parsing=True))

    if "hash" not in data:
        raise ValueError("Missing hash")

    received_hash = data.pop("hash")

    # TTL check
    auth_date = int(data.get("auth_date", "0"))
    if auth_date == 0 or time.time() - auth_date > ttl_sec:
        raise ValueError("initData expired")

    # Build data_check_string
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

