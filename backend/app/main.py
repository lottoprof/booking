# backend/app/main.py

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
)

app = FastAPI(title="Booking API")

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
