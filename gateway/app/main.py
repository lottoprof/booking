# gateway/app/main.py

import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import Response, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import TG_WEBHOOK_SECRET, REDIS_URL, DOMAIN_API_URL
from app.middleware.auth import auth_middleware
from app.middleware.rate_limit import rate_limit_middleware, check_tg_rate_limit
from app.middleware.access_policy import access_policy_middleware
from app.middleware.audit import audit_middleware
from app.proxy import proxy_request
from app.routers.web_booking import router as web_booking_router

from app.utils.telegram import (
    authenticate_tg_user,
    extract_tg_id,
)

# ВАЖНО: импорт на уровне модуля, НЕ внутри handler
from bot.app.main import process_update
from bot.app.utils.api import api
from bot.app.events.consumer import (
    p2p_consumer_loop,
    broadcast_consumer_loop,
    retry_consumer_loop,
)
from app.events.web_booking_consumer import web_booking_consumer_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    
    # Warmup: прогреваем Telegram API connection
    try:
        from bot.app.main import bot
        import time
        start = time.time()
        me = await bot.get_me()
        logger.info(f"Warmup: Telegram API ready in {time.time() - start:.2f}s (@{me.username})")
    except Exception as e:
        logger.error(f"Warmup failed: {e}")

    # Set default Mini App menu button (for new users before language selection)
    try:
        from bot.app.config import MINIAPP_URL
        from bot.app.i18n.loader import t, DEFAULT_LANG
        if MINIAPP_URL:
            from aiogram.types import MenuButtonWebApp, WebAppInfo
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=t("miniapp:menu_button", DEFAULT_LANG),
                    web_app=WebAppInfo(url=MINIAPP_URL),
                ),
            )
            logger.info(f"Default menu button set: {MINIAPP_URL}")
    except Exception as e:
        logger.warning(f"Failed to set default menu button: {e}")

    logger.info("Gateway started")

    # Start event consumer loops
    consumer_tasks = [
        asyncio.create_task(
            p2p_consumer_loop(REDIS_URL), name="p2p_consumer"
        ),
        asyncio.create_task(
            broadcast_consumer_loop(REDIS_URL), name="broadcast_consumer"
        ),
        asyncio.create_task(
            retry_consumer_loop(REDIS_URL), name="retry_consumer"
        ),
        asyncio.create_task(
            web_booking_consumer_loop(REDIS_URL, DOMAIN_API_URL),
            name="web_booking_consumer"
        ),
    ]
    logger.info("Event consumer loops started")

    yield

    # Shutdown: cancel consumer loops
    for task in consumer_tasks:
        task.cancel()
    await asyncio.gather(*consumer_tasks, return_exceptions=True)
    logger.info("Event consumer loops stopped")

    # Shutdown: закрываем API client
    await api.close()
    logger.info("API client closed")


app = FastAPI(title="Booking API Gateway", lifespan=lifespan)

# ===== Middleware order =====
app.middleware("http")(audit_middleware)
app.middleware("http")(access_policy_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(auth_middleware)

# ===== Web booking routes (Redis only, no auth required) =====
app.include_router(web_booking_router)


# ===== Static files for frontend =====
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

# Mount static directories (if they exist)
if (FRONTEND_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
if (FRONTEND_DIR / "images").exists():
    app.mount("/images", StaticFiles(directory=FRONTEND_DIR / "images"), name="images")
if (FRONTEND_DIR / "logo").exists():
    app.mount("/logo", StaticFiles(directory=FRONTEND_DIR / "logo"), name="logo")
if (FRONTEND_DIR / "blog").exists():
    app.mount("/blog", StaticFiles(directory=FRONTEND_DIR / "blog", html=True), name="blog")


# ===== HTML page routes =====
@app.get("/", include_in_schema=False)
async def serve_home():
    """Serve landing page."""
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Coming Soon</h1>", status_code=200)


@app.get("/book", include_in_schema=False)
async def serve_booking():
    """Serve booking page."""
    html_path = FRONTEND_DIR / "book.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Booking - Coming Soon</h1>", status_code=200)


@app.get("/pricing", include_in_schema=False)
async def serve_pricing():
    """Serve pricing page."""
    html_path = FRONTEND_DIR / "pricing.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Pricing - Coming Soon</h1>", status_code=200)


@app.get("/miniapp", include_in_schema=False)
async def serve_miniapp():
    """Serve Telegram Mini App page."""
    html_path = FRONTEND_DIR / "miniapp.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>Mini App - Coming Soon</h1>", status_code=200)


@app.get("/logo.svg", include_in_schema=False)
async def serve_logo():
    """Serve logo SVG (backwards compat: /logo.svg → /logo/logo.svg)."""
    svg_path = FRONTEND_DIR / "logo" / "logo.svg"
    if svg_path.exists():
        return FileResponse(svg_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404)


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
        logger.debug(f"Update keys: {list(update.keys())}")
    except Exception:
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
    asyncio.create_task(
        _safe_process_update(update, user_context),
        name=f"tg_update:{tg_id or 'unknown'}"
    )
    return {"ok": True}


async def _safe_process_update(update: dict, user_context):
    """Wrapper для process_update с обработкой ошибок."""
    try:
        await process_update(update, user_context)
    except Exception:
        logger.exception("Failed to process Telegram update")


# ===== OAuth callback (public route) =====
@app.get("/oauth/google/callback")
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter with encoded specialist_id"),
) -> HTMLResponse:
    """
    Handle OAuth callback from Google.

    This is a public endpoint that Google redirects to after authorization.
    It proxies the request to the backend for token exchange.
    """
    import httpx

    backend_url = f"{DOMAIN_API_URL}/integrations/google/callback"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                backend_url,
                params={"code": code, "state": state},
                timeout=30.0,
            )

        if response.status_code == 200:
            # Success - show nice page
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Google Calendar Connected</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .card {
                        background: white;
                        padding: 40px;
                        border-radius: 16px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    .icon { font-size: 64px; margin-bottom: 20px; }
                    h1 { color: #333; margin: 0 0 10px; font-size: 24px; }
                    p { color: #666; margin: 0; line-height: 1.6; }
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="icon">✅</div>
                    <h1>Google Calendar Connected!</h1>
                    <p>You can now close this window and return to Telegram.</p>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        else:
            # Error from backend
            error_detail = response.text
            logger.error(f"OAuth callback failed: {error_detail}")
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Connection Failed</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    }}
                    .card {{
                        background: white;
                        padding: 40px;
                        border-radius: 16px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }}
                    .icon {{ font-size: 64px; margin-bottom: 20px; }}
                    h1 {{ color: #333; margin: 0 0 10px; font-size: 24px; }}
                    p {{ color: #666; margin: 0; line-height: 1.6; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="icon">❌</div>
                    <h1>Connection Failed</h1>
                    <p>Please try again from the Telegram bot.</p>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=400)

    except Exception as e:
        logger.exception(f"OAuth callback error: {e}")
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Error</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                }
                .card {
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 400px;
                }
                .icon { font-size: 64px; margin-bottom: 20px; }
                h1 { color: #333; margin: 0 0 10px; font-size: 24px; }
                p { color: #666; margin: 0; line-height: 1.6; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">⚠️</div>
                <h1>Something Went Wrong</h1>
                <p>Please try again later.</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=500)


# ===== Catch-all proxy =====
@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def gateway_proxy(request: Request, path: str) -> Response:
    return await proxy_request(request)

