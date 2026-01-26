# Система нотификаций

## Версия: 2.0

---

## 1. Обзор

Универсальная система уведомлений всех участников (admin, specialist, client) через все каналы (Telegram, Web Push).

**Backend — единственный источник событий.** После бизнес-операции backend пушит событие в Redis. Consumer loops в gateway process читают очереди и доставляют уведомления.

**Каналы доставки:**
- Telegram (tg_id → bot.send_message)
- Web Push (push_subscription → pywebpush)

---

## 2. Архитектура

```
Backend API (booking created/cancelled/rescheduled)
    │
    └── RPUSH Redis
            │
    ┌───────┴────────┐
    ▼                ▼
events:p2p      events:broadcast
(instant)       (throttled 30/sec)
    │                │
    ▼                ▼
Consumer loops в gateway process (asyncio tasks в lifespan)
    │
    ├── notification_settings (БД) → enabled? ad_template?
    ├── resolve recipients → exclude initiator
    ├── format message + optional ad
    │
    ├── tg_id → bot.send_message()
    └── push_subscription → Web Push HTTP POST
```

**Фактическая архитектура:** Gateway вызывает bot напрямую через import (`from bot.app.main import process_update`). Redis-очередь между gateway и bot **не существует**. Redis используется только для event bus нотификаций.

---

## 3. Компоненты

### 3.1. Backend: Event Emitter

**Файл:** `backend/app/services/events.py`

- `emit_event(event_type, payload)` → `RPUSH events:p2p`
- `emit_broadcast(event_type, payload)` → `RPUSH events:broadcast`

**Формат события:**
```json
{
  "type": "booking_created",
  "booking_id": 123,
  "initiated_by": {"user_id": 45, "role": "client", "channel": "tg_bot"},
  "ts": 1706000000
}
```

`initiated_by` передаётся через HTTP headers:
- `X-Initiated-By-User-Id`
- `X-Initiated-By-Role`
- `X-Initiated-By-Channel`

### 3.2. Gateway: Consumer Loops

**Файл:** `bot/app/events/consumer.py`

- `p2p_consumer_loop()` — BRPOP events:p2p, без задержки
- `broadcast_consumer_loop()` — BRPOP events:broadcast, throttle 30 msg/sec
- `retry_consumer_loop()` — перемещает события из retry queue обратно в основную

**Retry логика:**
- При ошибке обработки → RPUSH events:p2p:retry (max 3 attempts)
- После 3 попыток → events:p2p:dead (dead-letter queue)

**Запуск:** asyncio.create_task() в gateway lifespan.

### 3.3. Bot: Event Dispatcher

**Файл:** `bot/app/events/__init__.py`

- Реестр `EVENT_HANDLERS` с декоратором `@register_event("booking_created")`
- `process_event(data)` — dispatch по `data["type"]`

### 3.4. Recipient Resolution

**Файл:** `bot/app/events/recipients.py`

- `resolve_recipients(event_type, booking, initiated_by)` → list[Recipient]
- Для каждой роли в notification_settings (enabled=1) → найти пользователей
- Исключить инициатора (initiated_by.user_id)

### 3.5. Message Formatting

**Файл:** `bot/app/events/formatters.py`

- Per event_type + per recipient_role форматирование
- HTML (parse_mode) для Telegram
- Опциональный ad_template блок

### 3.6. Delivery

**Файл:** `bot/app/events/delivery.py`

- `deliver_booking_event(event_type, data)` — main entry point
- `_send_telegram(tg_id, text, keyboard)` — bot.send_message()
- `_send_web_push(subscription, payload)` — pywebpush

---

## 4. Таблицы БД

### notification_settings

```sql
CREATE TABLE notification_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    recipient_role TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'all',
    enabled INTEGER NOT NULL DEFAULT 1,
    ad_template_id INTEGER,
    company_id INTEGER NOT NULL,
    UNIQUE(event_type, recipient_role, channel, company_id)
);
```

### ad_templates

```sql
CREATE TABLE ad_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content_tg TEXT NOT NULL,
    content_html TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    valid_until DATETIME,
    company_id INTEGER NOT NULL
);
```

### Seed data (дефолтные настройки)

| event_type | recipient_role | enabled |
|------------|---------------|---------|
| booking_created | admin | 1 |
| booking_created | specialist | 1 |
| booking_created | client | 1 |
| booking_cancelled | admin | 1 |
| booking_cancelled | specialist | 1 |
| booking_cancelled | client | 1 |
| booking_rescheduled | admin | 1 |
| booking_rescheduled | specialist | 1 |
| booking_rescheduled | client | 1 |

---

## 5. Матрица получателей

| Событие | initiated_by | → Client | → Specialist | → Admin |
|---------|-------------|----------|-------------|---------|
| booking_created | client | ✅ подтверждение | ✅ новая запись | ✅ новая запись |
| booking_created | admin | ✅ создана для вас | ✅ новая запись | ❌ сам |
| booking_cancelled | client | ❌ сам | ✅ отменена | ✅ отменена |
| booking_cancelled | admin | ✅ ваша запись отменена | ✅ отменена | ❌ сам |
| booking_cancelled | specialist | ✅ ваша запись отменена | ❌ сам | ✅ отменена |
| booking_rescheduled | admin | ✅ перенесена | ✅ перенесена | ❌ сам |
| booking_reminder | cron | ✅ напоминание | ✅ напоминание | ❌ |

**Канал доставки:** tg_id → Telegram; push_subscription (без tg_id) → Web Push.

---

## 6. Bot UI — кнопки уведомлений

### 6.1. Admin notification

```
📅 Новая запись #123

👤 Иван Петров
📞 +7 999 123-45-67
📍 Центр
💇 Стрижка · 60 мин
🕐 28.01.2026 14:00
👨‍💼 Анна

[✏️ Редактировать] [🙈 Скрыть]
```

### 6.2. Callbacks

**Notification callbacks (admin only):**
- `bkn:edit:{booking_id}` → меню редактирования
- `bkn:hide:{booking_id}` → удалить сообщение
- `bkn:back:{booking_id}` → вернуться к уведомлению

**Booking edit callbacks (all roles):**
- `bke:menu:{booking_id}:{return_to}` → меню редактирования
- `bke:cancel:{booking_id}:{return_to}` → подтверждение отмены
- `bke:confirm_cancel:{booking_id}:{return_to}` → выполнить отмену
- `bke:reschedule:{booking_id}` → начать перенос (FSM)

---

## 7. Web Push

**Зависимость:** `pywebpush` (в requirements.txt)

**ENV переменные:**
- `VAPID_PRIVATE_KEY` — приватный VAPID ключ
- `VAPID_PUBLIC_KEY` — публичный VAPID ключ
- `VAPID_EMAIL` — email для VAPID claims

Web Push используется как fallback для пользователей без tg_id (Mini App, Browser).

---

## 8. Файлы

| Файл | Описание |
|------|----------|
| `backend/app/services/events.py` | Event emitter (RPUSH → Redis) |
| `backend/app/routers/bookings.py` | Emit events after create/update |
| `backend/app/routers/notification_settings.py` | CRUD notification_settings |
| `backend/app/routers/ad_templates.py` | CRUD ad_templates |
| `backend/app/models/generated.py` | SQLAlchemy models |
| `backend/app/schemas/notification_settings.py` | Pydantic schemas |
| `backend/app/schemas/ad_templates.py` | Pydantic schemas |
| `backend/migrations/005_notification_tables.sql` | Migration |
| `bot/app/events/__init__.py` | Event dispatcher |
| `bot/app/events/booking.py` | Booking event handlers |
| `bot/app/events/consumer.py` | Redis consumer loops |
| `bot/app/events/delivery.py` | Telegram + Web Push delivery |
| `bot/app/events/recipients.py` | Recipient resolution |
| `bot/app/events/formatters.py` | Message formatting |
| `bot/app/flows/admin/booking_notify.py` | Admin notification callbacks |
| `bot/app/flows/common/booking_edit.py` | Reusable booking edit flow |
| `gateway/app/main.py` | Consumer loop startup in lifespan |

---

## 9. Верификация

1. Создать booking через API → событие в Redis (`LLEN events:p2p`) → consumer → Telegram
2. CRUD notification_settings → отключить роль → проверить что фильтрует
3. Создать/отменить/перенести booking → все участники получили уведомления
4. Проверить что инициатор исключён из получателей
5. Кнопки уведомления (Редактировать/Скрыть/Отменить/Перенести)
6. Web Push (если настроены VAPID ключи)
