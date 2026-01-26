# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A booking/scheduling system with Telegram bot integration. Three-tier architecture: Gateway (HTTP proxy) → Bot (UI layer) → Backend (business logic).

**Tech Stack:** Python 3.11+, FastAPI, aiogram 3, SQLite, Redis

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
python backend/migrate.py

# Initialize admin user (one-time setup)
python scripts/init_admin.py

# Start services with Docker
docker-compose up

# Start backend manually (port 8000)
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Start gateway manually (port 8080)
cd gateway && uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Architecture

### Component Flow
```
Telegram → NGINX → Gateway (/tg/webhook) → Redis Queue → Bot Worker → Backend API → SQLite/Redis
```

### Three Services

1. **backend/** - FastAPI business logic (port 8000)
   - Direct SQLite access via aiosqlite
   - Full Redis access (FSM, cache, locks)
   - 21 CRUD routers in `app/routers/`
   - Slot calculation engine in `app/services/slots/`

2. **gateway/** - FastAPI proxy (port 8080)
   - Single entry point for Telegram webhooks at `/tg/webhook`
   - Verifies `X-Telegram-Bot-Api-Secret-Token`
   - Rate limiting, authentication, audit logging
   - Enqueues updates to Redis; does NOT execute bot logic

3. **bot/** - aiogram 3 UI worker
   - Role-based handlers: admin, specialist, client
   - FSM stored in Redis (not memory)
   - Communicates only via backend API
   - No direct SQLite access

### Two-Level Slot Calculation

**Level 1 (Redis cache):** Location base grid
- Key: `slots:location:{location_id}:{date}`
- Value: 96-char string ("0"/"1" for each 15-min interval)
- Contains: location work_schedule + calendar_overrides
- Does NOT contain: bookings, specialists, rooms

**Level 2 (Runtime):** Calculated after service selection
- Applies specialist schedules and calendar_overrides
- Checks existing bookings
- Validates room availability if service requires rooms
- Double-checked with Redis lock during booking creation

### Key Directories

- `backend/app/services/slots/` - Slot calculation engine (calculator.py, availability.py)
- `backend/app/routers/` - 21 API endpoint files
- `backend/migrations/` - SQL migration files
- `bot/app/flows/` - FSM scenarios by role (admin/, client/, specialist/)
- `bot/app/handlers/` - Message and callback handlers
- `gateway/app/middleware/` - Auth, rate-limit, audit middleware

## Configuration

Environment variables in `.env`:
- `DATABASE_URL` - SQLite path (e.g., `sqlite:///./data/sqlite/booking.db`)
- `REDIS_URL` - Redis connection
- `TG_BOT_TOKEN` - Telegram bot token
- `TG_WEBHOOK_SECRET` - Webhook verification secret
- `DOMAIN_API_URL` - Backend URL (default: http://127.0.0.1:8000)
- `ADMIN_TG_ID` - Admin Telegram user ID

## Database

SQLite stored at `data/sqlite/booking.db`. Key tables:
- `users` - Unified entity for clients, specialists, admins
- `user_roles` - Role assignments with location
- `specialists` - Service providers with `work_schedule` JSON
- `locations` - Offices with `work_schedule` JSON
- `services` - Offered services (duration, break, price)
- `bookings` - Reservations with fixed duration/break at creation time
- `calendar_overrides` - Schedule exceptions

## Code Patterns

- SQL queries are manual via aiosqlite (not full ORM)
- Pydantic models for API request/response validation
- FSM must be in Redis only (never in-memory)
- Gateway never calls Telegram API directly
- All role-based access control enforced by backend
