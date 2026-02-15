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
Telegram → NGINX → Gateway (/tg/webhook) → Bot (direct import) → Backend API → SQLite/Redis
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
   - Calls bot directly via `from bot.app.main import process_update`
   - Runs event consumer loops (p2p, broadcast, retry) as asyncio tasks

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

## Quality Gate

After any code changes: `ruff check .`
Before marking task as done: `pyright`
Before commit/push: `pytest`

Tools: **Ruff** (linting), **Black** (formatting), **Pyright** (type checking). Venv: `source venv/bin/activate`.

## Code Patterns

- SQL queries are manual via aiosqlite (not full ORM)
- Pydantic models for API request/response validation
- FSM must be in Redis only (never in-memory)
- Gateway never calls Telegram API directly
- All role-based access control enforced by backend

## Mandatory Rules

### i18n — All User-Facing Text

**Never hardcode text** in bot handlers, keyboards, or notifications. All user-facing strings must use the i18n system:

- **Define keys** in `bot/app/i18n/messages.txt` with format: `{lang}:{key} | "{text}"`
- **Read text** via `t(key, lang)` from `bot/app/i18n/loader.py`
- **Filter by text** via `t_all(key)` for multi-language matching in handlers
- Default language: `ru` (fallback if lang is None)

```python
# WRONG — hardcoded text
await callback.answer("Услуга подтверждена", show_alert=True)
button = InlineKeyboardButton(text="✅ Да", callback_data="...")

# RIGHT — i18n keys
from bot.app.i18n.loader import t, DEFAULT_LANG
await callback.answer(t("notify:done:confirmed", lang), show_alert=True)
button = InlineKeyboardButton(text=t("common:yes", lang), callback_data="...")
```

### MenuController — Bot Keyboard Navigation

> **Полный контракт:** `docs/tg_kbrd.md` (v3.0). Перед любой работой с клавиатурами бота — **прочитай контракт целиком**. Ниже — краткая выжимка.

**Always use `MenuController`** (`bot/app/utils/menucontroller.py`) for sending and managing Telegram keyboards. Never call `bot.send_message()` with `reply_markup` directly in handlers — use the controller methods instead.

Key methods:
- `mc.show(message, kb)` — show ReplyKeyboard (deletes old menu, tracks anchor in Redis)
- `mc.show_inline_readonly(message, text, kb)` — show InlineKeyboard (readonly, keeps Reply menu)
- `mc.show_inline_input(message, text, kb)` — show InlineKeyboard (removes Reply menu for input)
- `mc.back_to_reply(callback_message, kb)` — return from Inline to Reply menu
- `mc.edit_inline(callback_message, text, kb)` — edit existing Inline message
- `mc.show_for_chat(bot, chat_id, kb)` — show ReplyKeyboard by chat_id (no Message object)
- `mc.send_inline_in_flow(bot, chat_id, text, kb)` — send Inline in FSM flow
- `mc.reset(chat_id)` — full navigation reset (for /start)

MenuController tracks message IDs in Redis (`tg:menu:{chat_id}`, `tg:inline:{chat_id}`) to properly clean up old messages.

**Strict prohibitions** (see `docs/tg_kbrd.md` §12 for full list):
- Never call `callback.message.edit_text()` or `callback.message.edit_reply_markup()` directly — use `mc.edit_inline()`
- Never use hardcoded emoji (`◀️`/`▶️`) for pagination — use `t("common:prev", lang)` / `t("common:next", lang)`
- Pagination must always have exactly 3 buttons: `[prev | page/total | next]` with disabled = `" "` + noop (see `docs/tg_kbrd.md` §15)

### Architecture Boundaries

- **Business logic** (scheduling, timers, status checks, data validation) belongs in **backend**, not in bot or gateway
- **Bot** is a UI layer only — it formats messages and handles user interaction via backend API
- **Gateway** is a proxy + middleware layer — auth, rate limiting, audit, event consumers

### Contract-First — `docs/contract.md`

**All structural changes must follow the contract.** Before changing DB schema, entity relationships, block boundaries, or business rules:

1. Update `docs/contract.md` (and linked docs: `docs/booking.md`, `docs/wallet.md`) first
2. Then implement the code changes

The contract defines three blocks (ВРЕМЯ, УСЛУГИ, ДЕНЬГИ), their boundaries, and entity relationships. Code must stay consistent with it.

### SQLite Timestamp Format

Always use `"%Y-%m-%d %H:%M:%S"` for timestamps. Never use `datetime.isoformat()` — it produces `T` separator and microseconds that are inconsistent with SQLite `CURRENT_TIMESTAMP`.

```python
# WRONG
obj.updated_at = datetime.utcnow().isoformat()  # → "2026-01-26T13:02:09.166084"

# RIGHT
obj.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")  # → "2026-01-26 13:02:09"
```
