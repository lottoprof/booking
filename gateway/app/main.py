# gateway/app/main.py

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import Response
import logging

from app.config import TG_WEBHOOK_SECRET
from app.middleware.auth import auth_middleware
from app.middleware.rate_limit import rate_limit_middleware, check_tg_rate_limit
from app.middleware.access_policy import access_policy_middleware
from app.middleware.audit import audit_middleware
from app.proxy import proxy_request

from app.utils.telegram import (
    authenticate_tg_user,
    extract_tg_id,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Booking API Gateway")

# ===== Middleware order =====
app.middleware("http")(audit_middleware)
app.middleware("http")(access_policy_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(auth_middleware)


# ===== Telegram webhook =====
@app.post("/tg/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    # 1. Проверка secret token
    if x_telegram_bot_api_secret_token != TG_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    # 2. Парсим update
    try:
        update = await request.json()
    except Exception:
        logger.info(f"Webhook update: {list(update.keys())}")
        return {"ok": True}

    # 3. Rate limit по tg_id
    tg_id = extract_tg_id(update)
    if tg_id:
        allowed, retry_after = check_tg_rate_limit(tg_id)
        if not allowed:
            logger.warning(f"TG webhook rate limited: tg_id={tg_id}")
            return {"ok": True}  # 200 чтобы Telegram не ретраил

    # 4. Аутентификация пользователя
    user_context = None
    if tg_id:
        try:
            user_context = await authenticate_tg_user(update)
        except Exception as e:
            logger.exception(f"TG auth failed: {e}")

    # 5. Передаём в bot
    try:
        from bot.app.main import process_update
        await process_update(update, user_context)
    except Exception:
        logger.exception("Telegram update processing failed")

    return {"ok": True}


# ===== Catch-all proxy =====
@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def gateway_proxy(request: Request, path: str) -> Response:
    return await proxy_request(request)

