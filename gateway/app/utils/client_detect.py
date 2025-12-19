# TG определяется корректно (initData)
# admin_bot и internal жёстко разделены
# public = всё остальное

from fastapi import Request


def detect_client_type(request: Request) -> str:
    """
    Определяет тип клиента ТОЛЬКО по источнику запроса.
    Никакой бизнес-логики и валидации.
    """

    headers = request.headers

    # 1. Internal service / cron
    if headers.get("X-Internal-Token"):
        return "internal"

    # 2. Telegram admin bot
    if headers.get("X-Admin-Token"):
        return "admin_bot"

    # 3. Telegram Mini App / TG client
    # Официальный и устойчивый признак
    if headers.get("X-TG-Init-Data") or headers.get("X-TG-User"):
        return "tg_client"

    # 4. Open booking (public)
    return "public"

