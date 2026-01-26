#  Architecture

---

## 1.  Технологический стек

* Python 3.11
* FastAPI — backend + gateway
* aiogram 3 — Telegram-бот (admin, specialist, client)
* SQLite — основная БД (SQLAlchemy + синхронные запросы, миграции скриптом)
* Redis — кеш слотов, FSM, UI-состояние, события, rate limiting
* Pydantic — валидация API request/response

---

## 2.  Взаимодействие компонентов

```
Telegram → NGINX → /tg/webhook → gateway → asyncio.create_task(process_update()) → bot → backend → SQLite / Redis
```

* Все входящие соединения идут через `gateway`
* Gateway импортирует `process_update` из bot на уровне модуля и вызывает как async task
* Redis-очередь между gateway и bot **не используется** (прямой вызов)
* `bot.main()` не запускается отдельно, а вызывается как библиотека
* `backend` работает с SQLite и Redis
* `Redis` используется и ботом, и backend'ом, но с разным уровнем доступа

> **TODO:** Выделение бота в отдельный процесс (worker) через Redis-очередь `tg:updates` — отложено.
> Если у вас сотни-тысячи пользователей — один процесс справится. Разделение оправдано при десятках тысяч update/min. Преждевременная оптимизация инфраструктуры.
> См. [TODO-bot-worker-separation.md](TODO-bot-worker-separation.md)

---

## 3.  Компоненты системы

### 3.1. backend

* FastAPI-приложение (port 8000)
* Работает с SQLite напрямую (SQLAlchemy + синхронные запросы)
* Выполняет:

  * расчёт слотов (`app/services/slots/`)
  * CRUD для всех сущностей (23 роутера в `app/routers/`)
  * валидацию данных (Pydantic)
  * emit событий в Redis (`app/services/events.py`)
  * фоновую проверку завершённых записей (`app/services/completion_checker.py`)
* Доступ к Redis: полный (кеш слотов, блокировки, события, дедупликация)
* Background tasks (lifespan):
  * `completion_checker_loop` — каждые 60 сек проверяет записи где `date_start + duration_minutes <= now`, эмитит `booking_done` в `events:p2p`. Дедупликация через Redis ключ `bkdone:sent:{booking_id}` (TTL 24ч)

### 3.2. gateway

* FastAPI-прокси (port 8080)
* `/tg/webhook` — точка входа Telegram
* Проверка `X-Telegram-Bot-Api-Secret-Token`
* Устанавливает `client_type = internal`
* Формирует payload Telegram update + TgUserContext
* Вызывает `bot.process_update()` через `asyncio.create_task()` (прямой import, не Redis-очередь)
* Не обращается к Telegram API напрямую

* Аутентификация TG-пользователей (get_or_create + role)
* Кэширование user context в Redis (TTL 10 мин)
* Rate limiting по tg_id (настраивается в middleware/rate_limit.py)
* Передача TgUserContext в bot

* **Event consumers**: В lifespan запускаются asyncio tasks для чтения событий из Redis:
  * `p2p_consumer_loop` — мгновенная доставка уведомлений (events:p2p)
  * `broadcast_consumer_loop` — throttled доставка (events:broadcast, 30 msg/sec)
  * `retry_consumer_loop` — повторная обработка failed events

### 3.2.1. Система нотификаций

```
Backend API (booking created/cancelled/rescheduled/done)
    |
    |-- bookings.py: emit при create/cancel/reschedule
    |-- completion_checker.py: emit booking_done (фоновый loop)
    |
    +-- RPUSH Redis
            |
    +-------+--------+
    v                v
events:p2p      events:broadcast
(instant)       (throttled 30/sec)
    |                |
    v                v
Consumer loops в gateway process (asyncio tasks в lifespan)
    |
    |-- notification_settings (БД) -> enabled? ad_template?
    |-- resolve recipients -> exclude initiator
    |-- format message (i18n) + optional ad
    |
    |-- tg_id -> bot.send_message()
    +-- push_subscription -> Web Push HTTP POST
```

**Таблицы БД:**
* `notification_settings` — настройки по event_type x recipient_role x channel
* `ad_templates` — рекламные вставки в уведомления

**Матрица получателей:**

| Событие | initiated_by | -> Client | -> Specialist | -> Admin |
|---------|-------------|----------|-------------|---------|
| booking_created | client | подтверждение | новая запись | новая запись |
| booking_created | admin | создана для вас | новая запись | - сам |
| booking_cancelled | client | - сам | отменена | отменена |
| booking_cancelled | admin | ваша запись отменена | отменена | - сам |
| booking_cancelled | specialist | ваша запись отменена | - сам | отменена |
| booking_rescheduled | admin | перенесена | перенесена | - сам |
| booking_done | system | - | - | карточка: Да/Нет |

**booking_done flow:** completion_checker в backend эмитит событие -> admin получает карточку записи с кнопками "Да" (status->done) / "Нет" (status->no_show).

**Каналы доставки:** tg_id -> Telegram; push_subscription (без tg_id) -> Web Push.

**Retry и DLQ:**
* events:p2p:retry / events:broadcast:retry — повторные попытки (до 3)
* events:p2p:dead / events:broadcast:dead — dead-letter queue

### 3.3. bot (Telegram)

* Bot работает **in-process с gateway** — импортируется на уровне модуля, вызывается через `asyncio.create_task(process_update())`
* Не имеет собственного webhook endpoint и не запускается отдельно

* aiogram 3 FSM-бот
* Поддерживает роли: `admin`, `specialist`, `client`
* FSM — только для сложных сценариев (не для навигации)
* MenuController (`bot/app/utils/menucontroller.py`) — управление клавиатурами через Redis
* i18n (`bot/app/i18n/`) — все тексты через `t(key, lang)`, ключи в `messages.txt`
* Обработка событий уведомлений (`bot/app/events/`) — форматирование и доставка
* Использует Redis:

  * `tg:menu:{chat_id}` — якорь Reply-клавиатуры
  * `tg:inline:{chat_id}` — список inline-сообщений
  * `tg:current_menu:{chat_id}` — контекст текущего меню
  * `fsm:*` — FSM состояния
* Работает только через backend API
* Не имеет доступа к SQLite

### 3.4. Redis

* Используется как shared runtime layer
* Ключи:

  * `tg:menu:{chat_id}` — якорь Reply-клавиатуры (MenuController)
  * `tg:inline:{chat_id}` — список inline-сообщений (MenuController)
  * `tg:current_menu:{chat_id}` — контекст текущего меню
  * `tg:init:{hash}` — auth init state (gateway middleware)
  * `fsm:*` — FSM состояния (aiogram Redis storage)
  * `otp:*`, `attempts:*` — OTP коды и счётчики попыток
  * `slots:location:{id}:{date}` — кэш слотов (96-char grid)
  * `slots:location:version:{id}` — версия для инвалидации
  * `slots:lock:{id}:{date}` — блокировка при создании записи (30 сек TTL)
  * `events:p2p` — очередь мгновенных уведомлений
  * `events:broadcast` — очередь throttled уведомлений
  * `events:*:retry` — повторные попытки (до 3)
  * `events:*:dead` — dead-letter queue
  * `bkdone:sent:{booking_id}` — дедупликация booking_done (24ч TTL)
  * `rl:*` — rate limiting (gateway)

* bot: доступ к `tg:*`, `fsm:*`
* backend: доступ к `slots:*`, `events:*`, `bkdone:*`, `otp:*`
* gateway: доступ к `tg:init:*`, `rl:*`, `events:*` (consumers)


### 3.5. SQLite

* Хранится в `data/sqlite/booking.db`
* Схема: `schema_sqlite.sql`, миграции — `backend/migrate.py` + `backend/migrations/*.sql`
* Используется **только backend**
* Блокировка при записи — через Redis lock (`slots:lock:{id}:{date}`, 30 сек TTL)
* Статусы записей: `pending` -> `confirmed` -> `done` / `cancelled` / `no_show`

---

## 4.  Telegram-бот: роли

| Роль       | Назначение                          | API | Redis | SQLite |
| ---------- | ----------------------------------- | --- | ----- | ------ |
| Admin      | Управление всей системой            | +   | +     | -      |
| Specialist | Просмотр личных записей, расписания | +   | +     | -      |
| Client     | Запись, просмотр, отмена            | +   | +     | -      |

* Все роли работают только через API backend
* Все ограничения по доступу определяются backend'ом

---

## 5. Структура проекта

```
backend/                          # Бизнес логика (port 8000)
  app/
    models/
    routers/                      # 23 CRUD + 2 domain роутера
    schemas/
    services/
      slots/                      # Расчёт слотов (L1 cache / L2 runtime)
      events.py                   # Emit событий в Redis
      completion_checker.py       # Фоновая проверка завершённых записей
    database.py
    redis_client.py
  migrate.py
  migrations/                     # SQL миграции (001-007)

bot/                              # UI — вызывается gateway (in-process)
  app/
    handlers/                     # reply / inline handlers
    flows/                        # FSM сценарии
      admin/                      # 19 модулей
      client/                     # 4 модуля
      specialist/                 # 2 модуля
      common/                     # booking_edit (переиспользуемый)
    events/                       # Система уведомлений
      consumer.py                 # Consumer loops (p2p, broadcast, retry)
      booking.py                  # Event handlers
      delivery.py                 # Доставка (Telegram, Web Push)
      formatters.py               # Форматирование (i18n)
      recipients.py               # Определение получателей
    i18n/                         # Интернационализация
      loader.py                   # t(key, lang), t_all(key)
      messages.txt                # {lang}:{key} | "{text}"
    keyboards/
    utils/
      menucontroller.py           # Управление клавиатурами (Redis)
      api.py                      # HTTP клиент к backend

gateway/                          # Webhook + прокси (port 8080)
  app/
    middleware/                    # auth, rate_limit, access_policy, audit
    policy/
    proxy.py
    utils/telegram.py

data/sqlite/                      # SQLite БД
scripts/                          # init_admin.py
docs/
```

---

## 6.  Инициализация и доступ администратора

* Скрипт `init_admin.py` выполняется один раз
* Прямой доступ к SQLite есть **только у скрипта** и backend
* После инициализации:

  * `tg_id` администратора сохранён в БД
  * bot/admin работает только через API
  * backend допускает только авторизованных `tg_id`

---

## 7.  Преимущества Gateway-centric архитектуры

| Аспект             | Gateway-centric                      |
| ------------------ | ------------------------------------ |
| Единая точка входа | Всё через gateway                    |
| Rate limiting      | Централизованный контроль            |
| Access policy      | Общая политика безопасности          |
| Audit log          | Централизованный лог                 |
| SSL/TLS            | Только на nginx                      |
| Масштабирование    | Многоклиентность через конфиг        |
| Несколько клиентов | tg_client, public                    |

Бот — чистый UI-слой, gateway — единая точка контроля.

---

# Telegram Gateway Architecture (Production)

## Назначение

Этот документ фиксирует **финальную архитектуру обработки Telegram-апдейтов** для production.

---

## Базовый принцип

* **Gateway управляет Telegram**: безопасность, аутентификация, rate-limit, аудит, контекст пользователя.
* **Bot — UI-воркер**: FSM, MenuController, обработка update и взаимодействие с Telegram API.
* **Связь gateway -> bot** через прямой import и `asyncio.create_task()`.

Webhook **никогда не выполняет бизнес-логику и не обращается к Telegram API**.

---

## Архитектурная схема

```
Telegram
   |
NGINX
   |
Gateway (/tg/webhook)
 |-- verify secret token
 |-- rate-limit / audit
 |-- authenticate TG user
 |-- build TgUserContext
 +-- asyncio.create_task(process_update())
        |
Bot (aiogram, in-process)
 |-- dp.feed_update(bot, update)
 |-- FSM (Redis)
 |-- MenuController
 +-- Telegram API
```

---

## Ответственность компонентов

### Gateway

Gateway — **единственная точка входа Telegram**.

Отвечает за:

* проверку `X-Telegram-Bot-Api-Secret-Token`
* rate-limit и защиту от флуда
* аудит и логирование
* определение `client_type = internal`
* аутентификацию пользователя и роли
* формирование `TgUserContext`
* вызов `process_update()` через asyncio task

**Gateway также запускает:**

* Event consumer loops (p2p, broadcast, retry) — обработка уведомлений из Redis

---

### Redis

Используется как **shared runtime layer**.

Ключи:

* `tg:menu:{chat_id}`, `tg:inline:{chat_id}`, `tg:current_menu:{chat_id}` — MenuController
* `fsm:*` — FSM состояния бота
* `events:p2p`, `events:broadcast` — очереди уведомлений
* `events:*:retry`, `events:*:dead` — retry и dead-letter queue
* `bkdone:sent:{booking_id}` — дедупликация booking_done
* `slots:location:{id}:{date}` — кэш слотов
* `slots:lock:{id}:{date}` — блокировка при записи
* `rl:*` — rate limiting

---

### Bot

Bot работает **in-process с gateway**, вызывается через import.

Отвечает за:

* обработку Telegram update через dispatcher
* FSM (через Redis)
* MenuController (управление клавиатурами через Redis)
* i18n (все тексты через `t(key, lang)`)
* общение с Telegram API
* обработку событий нотификаций (events module)

Bot **не знает** про gateway, HTTP, auth, rate-limit.

---

## Критические риски и как они закрыты

### 1. Асинхронность и отладка

**Риск:** потеря связности логов.

**Решение:**

* единый `trace_id` (tg update id или UUID)
* передаётся через gateway -> bot -> backend

---

### 2. Порядок сообщений (Telegram ordering)

**Риск:** race condition при параллельной обработке.

**Решение (принятое):**

* сериализация обработки **по chat_id**
* `asyncio.Lock` / `Semaphore` на chat_id

Гарантирует:

* сохранение порядка Telegram
* корректную работу FSM

---

### 3. FSM состояние

**Риск:** потеря состояния при рестарте или retry.

**Решение:**

* FSM **только в Redis**
* сериализация состояния
* TTL на ключи

FSM в памяти процесса **запрещён**.

---

### 4. Retry и DLQ

**Риск:** бесконечные падения или потеря update.

**Решение:**

* ограниченное число retry
* backoff
* `events:*:dead` для ручного анализа

DLQ — обязательный элемент production.

---

## Почему это не нарушает gateway-centric модель

Gateway по-прежнему:

* контролирует вход
* управляет доверием
* определяет контекст
* принимает все Telegram-запросы

Bot остаётся UI-модулем, как и было спроектировано.

---

## Минимальный production-чеклист

* [x] webhook отвечает < 50 ms (async task, не блокирует response)
* [x] gateway вызывает bot через asyncio.create_task (in-process)
* [x] FSM в Redis
* [x] Notification events через Redis queues (events:p2p, events:broadcast)
* [x] retry + DLQ для notification events
* [x] i18n для всех user-facing текстов
* [x] MenuController для управления клавиатурами
* [x] completion_checker для автоматического booking_done

---

## Статус

Изменения возможны только при масштабировании (шардирование очередей), без изменения базовых принципов.
