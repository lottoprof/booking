import hashlib
import json
import time

from app.config import TG_BOT_TOKEN
from app.utils.client_detect import detect_client_type
from app.utils.telegram import verify_init_data
from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

ANTI_REPLAY_TTL = 60
INITDATA_TTL = 1800  # 30 минут

_BLOCKED_UA = ("curl/", "python-requests", "wget", "go-http-client", "scrapy")


def _deny(status: int = 403, detail: str = "Forbidden") -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def _initdata_key(init_data: str) -> str:
    h = hashlib.sha256(init_data.encode()).hexdigest()
    return f"tg:init:{h}"


async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # ===== Telegram webhook (trusted external entry) =====
    if path == "/tg/webhook":
        # auth выполнен ранее по X-Telegram-Bot-Api-Secret-Token
        request.state.client_type = "internal"
        return await call_next(request)

    client_type = detect_client_type(request)
    request.state.client_type = client_type

    # ===== Block scanners / bots on public requests =====
    if client_type == "public":
        if path.endswith(".php"):
            return _deny()

        ua = (request.headers.get("User-Agent") or "").lower()
        if not ua or any(b in ua for b in _BLOCKED_UA):
            return _deny()

    if client_type == "tg_client":
        init_data = request.headers.get("X-TG-Init-Data")
        if not init_data:
            raise HTTPException(401, "Missing TG initData")

        if not TG_BOT_TOKEN:
            raise HTTPException(500, "Internal server error")

        try:
            data = verify_init_data(init_data, TG_BOT_TOKEN)
        except ValueError as e:
            raise HTTPException(401, str(e)) from None

        # ===== ЖЁСТКАЯ TTL ПРОВЕРКА =====
        auth_date = int(data.get("auth_date", 0))
        if auth_date == 0 or time.time() - auth_date > INITDATA_TTL:
            raise HTTPException(401, "initData expired")

        # ===== NORMALIZED IDENTITY =====
        user_raw = data.get("user") or "{}"
        user = json.loads(user_raw) if isinstance(user_raw, str) else user_raw
        request.state.identity = {
            "tg_id": user.get("id"),
            "username": user.get("username"),
            "auth_date": auth_date,
        }

    return await call_next(request)
