# backend/app/main.py

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routers import (
    company,
    locations,
    rooms,
    roles,
    users,
    user_roles,
    services,
    service_packages,
    service_rooms,
    specialists,
    calendar_overrides,
    bookings,
    client_packages,
    client_discounts,
    booking_discounts,
    client_wallets,
    wallet_transactions,
    push_subscriptions,
    audit_log,
    notification_settings,
    ad_templates,
    wallets,
    slots,
    integrations,
    internal,
)
from .database import get_db
from .services.completion_checker import completion_checker_loop
from .services.reminder_checker import reminder_checker_loop
from .services.web_cache import rebuild_services_cache

logger = logging.getLogger(__name__)


def _warmup_web_caches():
    """Pre-fill Redis cache so gateway never hits backend on read."""
    db = next(get_db())
    try:
        rebuild_services_cache(db)
        logger.info("Web services cache warmed up")
    except Exception:
        logger.exception("Failed to warm up web services cache")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start background tasks."""
    _warmup_web_caches()
    checker_task = asyncio.create_task(
        completion_checker_loop(), name="completion_checker"
    )
    reminder_task = asyncio.create_task(
        reminder_checker_loop(), name="reminder_checker"
    )
    logger.info("Completion checker and reminder checker started")

    yield

    checker_task.cancel()
    reminder_task.cancel()
    await asyncio.gather(checker_task, reminder_task, return_exceptions=True)
    logger.info("Completion checker and reminder checker stopped")


app = FastAPI(title="Booking API", lifespan=lifespan)

# ──────────────────────────────────────────────────────────────────────────────
# CRUD Routers
# ──────────────────────────────────────────────────────────────────────────────
app.include_router(company.router)
app.include_router(locations.router)
app.include_router(rooms.router)
app.include_router(roles.router)
app.include_router(users.router)
app.include_router(user_roles.router)
app.include_router(services.router)
app.include_router(service_packages.router)
app.include_router(service_rooms.router)
app.include_router(specialists.router)
app.include_router(calendar_overrides.router)
app.include_router(bookings.router)
app.include_router(client_packages.router)
app.include_router(client_discounts.router)
app.include_router(booking_discounts.router)
app.include_router(client_wallets.router)
app.include_router(wallet_transactions.router)
app.include_router(push_subscriptions.router)
app.include_router(notification_settings.router)
app.include_router(ad_templates.router)
app.include_router(audit_log.router)

# ──────────────────────────────────────────────────────────────────────────────
# Domain API Routers
# ──────────────────────────────────────────────────────────────────────────────
app.include_router(wallets.router)
app.include_router(slots.router)
app.include_router(integrations.router)

# ──────────────────────────────────────────────────────────────────────────────
# Internal API (trusted consumers only, not proxied through gateway)
# ──────────────────────────────────────────────────────────────────────────────
app.include_router(internal.router)
