# TODO: Выделение бота в отдельный процесс (worker)

**Статус:** Отложено
**Причина:** Текущая нагрузка не требует. Если у вас сотни-тысячи пользователей — один процесс справится. Разделение оправдано при десятках тысяч update/min. Преждевременная оптимизация инфраструктуры.

---

## Целевая архитектура

```
Telegram
   ↓
NGINX
   ↓
Gateway (/tg/webhook)
 ├─ verify secret token
 ├─ rate‑limit / audit
 ├─ authenticate TG user
 ├─ build TgUserContext
 └─ RPUSH tg:updates → Redis
        ↓
     Redis Queue
        ↓
Bot Worker (отдельный процесс)
 ├─ BRPOP tg:updates
 ├─ dp.feed_update(bot, update)
 ├─ FSM (Redis)
 ├─ MenuController
 └─ Telegram API
```

---

## Что нужно сделать

### 1. Gateway: заменить прямой вызов на очередь

**Файл:** `gateway/app/main.py`

- Убрать `from bot.app.main import process_update`
- Вместо `asyncio.create_task(process_update())` → `RPUSH tg:updates` с сериализованным payload
- Payload: `{"trace_id": ..., "update": {...}, "user_context": {...}, "meta": {"attempt": 1, "ts": ...}}`
- TgUserContext сериализовать в JSON (сейчас передаётся по ссылке)

### 2. Bot: добавить consumer loop для Telegram updates

**Файл:** `bot/app/events/consumer.py` (или отдельный `bot/app/tg_consumer.py`)

- `tg_consumer_loop()` — BRPOP `tg:updates`, десериализация, вызов `process_update()`
- Сериализация по `chat_id` через `asyncio.Lock` per chat_id — гарантия порядка обработки
- Retry: `tg:updates:retry` (max 3) → `tg:updates:dead`

### 3. Bot: отдельный entrypoint

**Файл:** `bot/worker.py` (NEW)

```python
async def main():
    # Инициализация
    # Запуск tg_consumer_loop()
    # Запуск p2p_consumer_loop() — перенести из gateway
    # Запуск broadcast_consumer_loop() — перенести из gateway
```

### 4. Docker: отдельный контейнер

**Файл:** `docker-compose.yml`

```yaml
bot:
  build: .
  command: python -m bot.worker
  depends_on: [redis, backend]
```

### 5. Сериализация TgUserContext

Сейчас — dataclass в памяти. Нужно:
- JSON сериализация в gateway при RPUSH
- JSON десериализация в bot при BRPOP
- Валидация через Pydantic или dataclass

### 6. Сквозной trace_id

- Gateway генерирует `trace_id` (Telegram update_id или UUID)
- Передаётся через Redis → bot → backend (в headers)
- Централизованное логирование

### 7. Lock по chat_id

При нескольких воркерах — сообщения одного чата могут обрабатываться параллельно.

Решения:
- `asyncio.Lock` per chat_id (если один воркер)
- Шардирование очередей по `chat_id % N` (если несколько воркеров)
- Redis-lock per chat_id (распределённый вариант)

---

## Когда делать

Триггеры для реализации:

- Webhook начинает отвечать > 5 секунд
- Наблюдаются таймауты Telegram API
- Нужен zero-downtime деплой бота
- Нагрузка приближается к десяткам тысяч update/min
- Нужно горизонтальное масштабирование bot-воркеров

---

## Что уже готово

- Redis инфраструктура есть
- FSM уже в Redis (не in-memory)
- Consumer loop паттерн написан (`bot/app/events/consumer.py`)
- Event bus для нотификаций работает через Redis
- Bot общается с backend только через HTTP API (нет прямых SQLite-запросов)

---

## Риски

| Риск | Митигация |
|------|-----------|
| Порядок сообщений | Lock по chat_id / шардирование |
| Потеря связности логов | Сквозной trace_id |
| Потеря FSM при рестарте | FSM в Redis (уже) |
| Усложнение отладки | Централизованные логи |
| Латентность +1-3ms | Несущественно для Telegram-бота |
