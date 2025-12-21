from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import Response
from typing import Optional

from app.config import TG_WEBHOOK_SECRET
from app.middleware.auth import auth_middleware
from app.middleware.rate_limit import rate_limit_middleware
from app.middleware.access_policy import access_policy_middleware
from app.middleware.audit import audit_middleware
from app.proxy import proxy_request

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
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    if not TG_WEBHOOK_SECRET:
        raise HTTPException(500, "TG_WEBHOOK_SECRET not configured")

    if x_telegram_bot_api_secret_token != TG_WEBHOOK_SECRET:
        raise HTTPException(403, "Invalid Telegram secret")

    update = await request.json()

    # временно — только лог
    print("TG UPDATE:", update)

    return {"ok": True}


# ===== Catch-all proxy =====
@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def gateway_proxy(request: Request, path: str) -> Response:
    return await proxy_request(request)

