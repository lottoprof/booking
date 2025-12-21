from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import Response
import logging

from app.config import TG_WEBHOOK_SECRET
from app.middleware.auth import auth_middleware
from app.middleware.rate_limit import rate_limit_middleware
from app.middleware.access_policy import access_policy_middleware
from app.middleware.audit import audit_middleware
from app.proxy import proxy_request

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
    if x_telegram_bot_api_secret_token != TG_WEBHOOK_SECRET:
        raise HTTPException(status_code=403)

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    try:
        # Lazy import — избегаем circular dependency
        from bot.app.main import process_update
        await process_update(update)
    except Exception:
        logger.exception("Telegram update processing failed")

    return {"ok": True}


# ===== Catch-all proxy =====
@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def gateway_proxy(request: Request, path: str) -> Response:
    return await proxy_request(request)

