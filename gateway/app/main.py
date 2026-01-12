# gateway/app/main.py

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import Response
from contextlib import asynccontextmanager
import logging
import asyncio

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

# ВАЖНО: импорт на уровне модуля, НЕ внутри handler
from bot.app.main import process_update, bot
from bot.app.utils.api import api

logger = logging.getLogger(__name__)

# Background task handle
_keepalive_task: asyncio.Task | None = None


async def warmup():
    """
    Прогрев connections при старте.
    Инициализирует все lazy connections до первого пользователя.
    """
    logger.info("Starting warmup...")
    
    try:
        # 1. Прогреваем Telegram API connection (aiohttp внутри aiogram)
        me = await bot.get_me()
        logger.info(f"Telegram API ready: @{me.username}")
    except Exception as e:
        logger.error(f"Telegram API warmup failed: {e}")
    
    try:
        # 2. Прогреваем Backend API connection (httpx)
        company = await api.get_company()
        if company:
            logger.info(f"Backend API ready: company={company.get('name', 'OK')}")
        else:
            logger.warning("Backend API ready but no company found")
    except Exception as e:
        logger.error(f"Backend API warmup failed: {e}")
    
    logger.info("Warmup completed")


async def keepalive_loop():
    """
    Периодический ping для поддержания connections.
    Запускается в background, пингует каждые 5 минут.
    """
    while True:
        await asyncio.sleep(300)  # 5 минут
        
        try:
            # Ping Telegram API
            await bot.get_me()
            logger.debug("Keepalive: Telegram API OK")
        except Exception as e:
            logger.warning(f"Keepalive: Telegram API failed: {e}")
        
        try:
            # Ping Backend API
            await api.get_company()
            logger.debug("Keepalive: Backend API OK")
        except Exception as e:
            logger.warning(f"Keepalive: Backend API failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    global _keepalive_task
    
    # Startup
    await warmup()
    _keepalive_task = asyncio.create_task(keepalive_loop(), name="keepalive")
    logger.info("Keepalive task started")
    
    yield
    
    # Shutdown
    if _keepalive_task:
        _keepalive_task.cancel()
        try:
            await _keepalive_task
        except asyncio.CancelledError:
            pass
        logger.info("Keepalive task stopped")
    
    # Close API client
    await api.close()
    logger.info("API client closed")


app = FastAPI(title="Booking API Gateway", lifespan=lifespan)

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


# ===== Catch-all proxy =====
@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def gateway_proxy(request: Request, path: str) -> Response:
    return await proxy_request(request)
