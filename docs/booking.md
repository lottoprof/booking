# Booking & Slots Module — Architecture

## Версия документа: 1.5
## Статус: Актуализировано 2026-01-30

---

## 1. Обзор

Модуль управления слотами и бронированием — ядро системы записи.

**Основные принципы:**
- SQLite — источник истины (bookings, schedules, overrides)
- Redis — runtime-слой (сетка слотов, блокировки)
- Backend — единственный компонент с доступом к расчёту слотов
- Клиенты (bot, web) — только читают готовую сетку через API

---

## 2. Конфигурация системы

### 2.1. UI-ограничения (настраиваемые)

Хранятся в `company` или отдельной таблице `booking_config`:

```python
class BookingConfig:
    # Глубина расчёта (дней вперёд)
    horizon_days: int = 60          # варианты: 30, 60, 90
    
    # Минимальное время до записи (часов)
    min_advance_hours: int = 6      # варианты: 1, 6, 12, 24
    
    # Шаг сетки (минут) — фиксированный
    slot_step_min: int = 15
```

**Пример `min_advance_hours = 12`:**
```
Текущее время: 2025-01-20 00:00
Первый доступный слот: 2025-01-20 12:00

Текущее время: 2025-01-20 14:30
Первый доступный слот: 2025-01-21 02:30 → округляем до 03:00
```

### 2.2. Базовые параметры сетки

| Параметр | Значение | Настраиваемый |
|----------|----------|---------------|
| **Шаг сетки** | 15 минут | ❌ Фиксированный |
| **Ячеек в дне** | 96 | ❌ Вычисляемый |
| **Горизонт** | 30/60/90 дней | ✅ `horizon_days` |
| **Мин. время до записи** | 1/6/12/24 часа | ✅ `min_advance_hours` |

### 2.3. Индексация слотов

```
Индекс слота = (час × 4) + (минута ÷ 15)

00:00 → 0
00:15 → 1
00:30 → 2
00:45 → 3
01:00 → 4
...
23:45 → 95
```

### 2.3. Округление длительности

Длительность услуги округляется **вверх** до ближайших 15 минут:
- 30 мин → 2 слота
- 45 мин → 3 слота
- 50 мин → 4 слота (60 мин)
- 90 мин → 6 слотов

**Формула:** `slots_needed = ceil(duration_min / 15)`

---

## 3. Архитектура хранения

### 3.1. SQLite (источник истины)

```
┌─────────────────────────────────────────────────────────┐
│                      SQLite                             │
├─────────────────────────────────────────────────────────┤
│ locations.work_schedule    JSON  │ График локации       │
│ specialists.work_schedule  JSON  │ График специалиста   │
│ calendar_overrides              │ Исключения           │
│ bookings                        │ Бронирования         │
│ services.duration_min           │ Длительность услуги  │
│ services.break_min              │ Перерыв после услуги │
└─────────────────────────────────────────────────────────┘
```

### 3.2. Redis (runtime-слой)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Redis                                   │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 1 (базовая сетка локации):                               │
│   slots:day:{location_id}:{date}  ZSET   │ Sorted Set слотов   │
│     member = "HH:MM", score = expire_ts  │ (время, timestamp)  │
├─────────────────────────────────────────────────────────────────┤
│ LOCKS (при бронировании):                                       │
│   slots:lock:{specialist_id}:{date}      │ Lock на специалиста │
└─────────────────────────────────────────────────────────────────┘
```

**Примечание:** Level 2 (гранулярный расчёт) НЕ кешируется в Redis.
Он вычисляется на лету, так как зависит от конкретной услуги и
комбинации специалистов/кабинетов.

## 4. Формат данных в Redis

### 4.1. Выбранный формат: Sorted Set (ZSET)

**Ключ:** `slots:day:{location_id}:{YYYY-MM-DD}`

**Значение:** Sorted Set где:
- **Member** = "HH:MM" (время слота)
- **Score** = expire_ts (unix timestamp когда слот перестаёт быть доступным)

```
ZRANGE slots:day:1:2026-02-03 0 -1 WITHSCORES
→ "10:00" 1770058800
→ "10:30" 1770060600
→ "11:00" 1770062400
...

expire_ts = (slot_datetime − min_advance_hours).timestamp()
```

**Sentinel для пустых дней:** `__empty__` с score=0 означает "день рассчитан, слотов нет"

**Запрос живых слотов:**
```
ZRANGEBYSCORE slots:day:{loc}:{date} {now_ts} +inf
```
Возвращает только слоты, которые ещё можно забронировать.

### 4.2. Обоснование выбора

| Критерий | Sorted Set | String "0/1" | JSON |
|----------|------------|--------------|------|
| Автоматическое истечение слотов | ✅ ZRANGEBYSCORE | ❌ Ручная фильтрация | ❌ Ручная |
| Debug в redis-cli | ✅ ZRANGE | ✅ GET | ✅ GET |
| Память | ~2 KB/день | ~96 B/день | ~500 B/день |
| Сложность фильтрации | O(log N) | O(N) | O(N) |
| **Выбор** | ✅ | — | — |

**Преимущество Sorted Set:** слоты автоматически "истекают" без удаления — `ZRANGEBYSCORE` фильтрует по score.

### 4.3. Работа с Sorted Set в Python

```python
# backend/app/services/slots/redis_store.py

class SlotsRedisStore:
    KEY_PREFIX = "slots:day"

    def _key(self, location_id: int, dt: date) -> str:
        return f"{self.KEY_PREFIX}:{location_id}:{dt.isoformat()}"

    def store_day_slots(self, location_id, dt, slots: list[tuple[str, float]]):
        """Store slots as (time_str, expire_ts) pairs."""
        key = self._key(location_id, dt)
        pipe = self.redis.pipeline()
        pipe.delete(key)

        if slots:
            mapping = {time_str: expire_ts for time_str, expire_ts in slots}
            pipe.zadd(key, mapping)
            max_expire = max(exp for _, exp in slots)
            pipe.expireat(key, int(max_expire) + 60)
        else:
            pipe.zadd(key, {"__empty__": 0})

        pipe.execute()

    def get_available_slots(self, location_id, dt, now) -> list[str] | None:
        """Get slots where expire_ts > now."""
        key = self._key(location_id, dt)
        if not self.redis.exists(key):
            return None  # Cache miss

        now_ts = now.timestamp()
        members = self.redis.zrangebyscore(key, now_ts, "+inf")
        return [m for m in members if m != "__empty__"]
```

### 4.4. TTL и инвалидация

| Ключ | TTL | Инвалидация |
|------|-----|-------------|
| `slots:day:{id}:{date}` | До max(expire_ts) + 60 сек | При изменении schedule/override |
| `slots:lock:{id}:{date}` | 30 секунд | Автоматически |

**Автоматический TTL:** ключ живёт пока последний слот не истечёт.

### 4.5. Оптимизация: Batch операции

```python
# Batch подсчёт для календаря
def mget_counts(location_id, dates, now) -> dict[date, int | None]:
    now_ts = now.timestamp()
    pipe = redis.pipeline()

    for dt in dates:
        key = f"slots:day:{location_id}:{dt}"
        pipe.zcount(key, now_ts, "+inf")

    return dict(zip(dates, pipe.execute()))
```

### 4.6. Оценка нагрузки

| Сценарий | Локации | Память | IOPS (пик) |
|----------|---------|--------|------------|
| Small | 10 | ~200 KB | ~6 ops/s |
| Medium | 100 | ~2 MB | ~57 ops/s |
| Large | 1000 | ~20 MB | ~570 ops/s |

**Redis легко справляется** — типичный Redis обрабатывает 100,000+ ops/s.

---

## 5. Двухуровневая архитектура расчёта

### 5.1. Концепция

```
┌─────────────────────────────────────────────────────────────────┐
│              БАЗОВАЯ СЕТКА (опорная, Level 1)                   │
│                                                                 │
│  = Локация РАБОТАЕТ или НЕТ                                    │
│  = work_schedule + calendar_overrides + min_advance_hours       │
│                                                                 │
│  ✓ Кешируется в Redis                                          │
│  ✓ НЕ зависит от услуги                                        │
│  ✓ НЕ показывается клиенту напрямую                            │
│                                                                 │
│  ✗ НЕ содержит: bookings, специалистов, комнаты                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ (после выбора услуги клиентом)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              ГРАНУЛЯРНЫЙ РАСЧЁТ (видимый, Level 2)              │
│                                                                 │
│  = Базовая сетка AND специалисты AND комнаты AND bookings      │
│                                                                 │
│  ✓ Считается на лету                                           │
│  ✓ Зависит от service_id                                       │
│  ✓ ЭТО показывается клиенту                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Почему два уровня?**
- Базовая сетка стабильна (меняется редко — только schedule/overrides)
- Bookings не инвалидируют базовую сетку
- Level 2 всегда актуален (считается на лету с учётом bookings)

---

### 5.2. LEVEL 1: Базовая сетка локации

**Что содержит:**
```
✓ work_schedule локации
✓ calendar_overrides локации
✓ min_advance_hours

✗ Bookings — НЕ включаем
✗ Специалисты — НЕ включаем  
✗ Комнаты — НЕ включаем
```

**Входные данные:**
```python
def calculate_day_slots(
    db: Session,
    location_id: int,
    target_date: date,
    config: BookingConfig,
    now: datetime,
) -> list[tuple[str, float]]:
    """
    Базовая сетка локации на день.
    Возвращает список (time_str, expire_ts).

    time_str = "HH:MM" — время слота
    expire_ts = unix timestamp когда слот истекает
                (slot_datetime − min_advance_hours)

    Пустой список = локация закрыта в этот день.
    """
```

**Алгоритм:**

```
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: Проверить calendar_overrides                         │
│         WHERE target_type = 'location'                       │
│         AND target_id = location_id                          │
│         AND date BETWEEN date_start AND date_end             │
│         Если есть override → вернуть []                      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: Получить рабочие интервалы из work_schedule          │
│         location.work_schedule[weekday]                      │
│         Если нет интервалов → вернуть []                     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: Генерировать слоты с expire_ts                       │
│         Для каждого интервала [start, end]:                  │
│           t = start                                          │
│           while t < end:                                     │
│             expire_ts = (slot_dt − min_advance_hours).ts     │
│             if expire_ts > now_ts:                           │
│               slots.append((time_str, expire_ts))            │
│             t += 15 min                                      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ RESULT: [("10:00", 1770037200), ("10:15", 1770038100), ...]  │
│         Слоты с их expire timestamps                         │
└──────────────────────────────────────────────────────────────┘
```

**Пример min_advance_hours:**
```python
# Сейчас 2025-01-20 14:35, min_advance_hours = 6
# Слот 10:00 → expire_ts = 04:00 (уже прошло) → не включаем
# Слот 21:00 → expire_ts = 15:00 (ещё впереди) → включаем

for t in range(start_min, end_min, step):
    slot_dt = datetime.combine(date, time(0)) + timedelta(minutes=t)
    expire_ts = (slot_dt - timedelta(hours=min_advance_hours)).timestamp()
    if expire_ts > now.timestamp():
        slots.append((minutes_to_time_str(t), expire_ts))
```

---

### 5.3. LEVEL 2: Гранулярный расчёт для услуги

**Что содержит:**
```
✓ Базовая сетка (Level 1)
✓ Специалисты услуги + их графики + их overrides
✓ Комнаты услуги + их overrides
✓ Bookings специалистов
✓ Bookings комнат (занятость)
```

**Входные данные:**
```python
def calculate_service_availability(
    location_id: int,
    service_id: int,
    date: date
) -> ServiceAvailability:
    """
    Детальная доступность для конкретной услуги.
    Вызывается ПОСЛЕ выбора услуги клиентом.
    """
```

**Алгоритм:**

```
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: Получить базовую сетку локации (из Redis или calc)   │
│         base_grid = get_or_calculate(location_id, date)      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: Найти специалистов услуги                            │
│         SELECT specialist_id FROM specialist_services        │
│         WHERE service_id = X AND is_active = 1               │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: Для КАЖДОГО специалиста построить его сетку          │
│                                                              │
│   3a. Начать с base_grid (локация открыта?)                  │
│                                                              │
│   3b. Применить график специалиста                           │
│       specialist.work_schedule[weekday]                      │
│                                                              │
│   3c. Применить calendar_overrides специалиста               │
│       WHERE target_type = 'specialist'                       │
│                                                              │
│   3d. Применить bookings специалиста                         │
│       WHERE specialist_id = X AND date = Y                   │
│       AND status IN ('pending', 'confirmed')                 │
│       Закрыть: duration_minutes + break_minutes              │
│                                                              │
│   specialist_grid[spec_id] = результат                       │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 4: Найти комнаты для услуги                             │
│         SELECT room_id FROM service_rooms                    │
│         WHERE service_id = X AND is_active = 1               │
│                                                              │
│   Если service_rooms ПУСТО → комната НЕ нужна, пропускаем    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 5: Для КАЖДОЙ комнаты построить её сетку                │
│         (только если service_rooms НЕ пусто)                 │
│                                                              │
│   5a. Применить calendar_overrides комнаты                   │
│       WHERE target_type = 'room'                             │
│                                                              │
│   5b. Применить bookings в этой комнате                      │
│       WHERE room_id = X AND date = Y                         │
│       AND status IN ('pending', 'confirmed')                 │
│                                                              │
│   room_grid[room_id] = результат                             │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 6: Собрать итоговую доступность                         │
│                                                              │
│   Для каждого слота:                                         │
│   - free_specialists = спецы где grid[slot] == "1"           │
│   - free_rooms = комнаты где grid[slot] == "1" (или все)     │
│                                                              │
│   Слот доступен если:                                        │
│   - len(free_specialists) >= 1                               │
│   - len(free_rooms) >= 1 (или комнаты не нужны)              │
│   - Достаточно последовательных слотов для услуги            │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ RESULT: ServiceAvailability                                  │
│   - available_starts: list[int]  (индексы слотов)            │
│   - specialists_by_slot: dict[int, list[specialist]]         │
│   - rooms_by_slot: dict[int, list[room]]                     │
└──────────────────────────────────────────────────────────────┘
```

---

### 5.4. Структуры данных

```python
@dataclass
class ServiceAvailability:
    """Результат гранулярного расчёта."""
    location_id: int
    service_id: int
    date: date
    service_duration_min: int
    slots_needed: int
    
    # Слоты, доступные для начала записи
    available_starts: list[int]  # индексы слотов
    
    # Какие специалисты доступны в каждом слоте
    specialists_by_slot: dict[int, list[int]]
    
    # Какие кабинеты доступны в каждом слоте  
    rooms_by_slot: dict[int, list[int]]


@dataclass
class DayAvailability:
    """Доступность дня для UI (Level 1)."""
    date: date
    is_available: bool          # есть хотя бы один открытый слот
    open_slots_count: int       # сколько слотов открыто
    first_available_slot: int | None
    last_available_slot: int | None
```

---

### 5.5. UX Flow и точки расчёта

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ВЫБОР УСЛУГИ                                                 │
│                                                                 │
│    UI показывает список услуг                                   │
│    Расчёт: НЕТ (только читаем services)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. ВЫБОР ДНЯ                                                    │
│                                                                 │
│    UI показывает календарь на horizon_days дней                │
│    Расчёт: Level 1 для каждого дня                             │
│                                                                 │
│    День доступен, если location_grid содержит хотя бы одну "1" │
│    Пример: день 16:00-19:00 открыт → день кликабелен           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. ВЫБОР ВРЕМЕНИ                                                │
│                                                                 │
│    UI показывает доступные слоты выбранного дня                │
│    Расчёт: Level 2 (гранулярный)                               │
│                                                                 │
│    Учитываются: специалисты услуги, их графики, кабинеты       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. ВЫБОР СПЕЦИАЛИСТА (если несколько)                          │
│                                                                 │
│    specialists_by_slot[selected_slot] = [5, 7, 12]             │
│                                                                 │
│    Если len == 1: автоматический выбор → подтверждение         │
│    Если len > 1: UI показывает список специалистов             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. ПОДТВЕРЖДЕНИЕ                                                │
│                                                                 │
│    POST /bookings с выбранными параметрами                     │
│    Lock → Double-check → Insert → Invalidate                   │
└─────────────────────────────────────────────────────────────────┘
```

---

### 5.6. Формат work_schedule (JSON)

```json
{
  "0": [["09:00", "18:00"]],                    // Пн: 09:00-18:00
  "1": [["09:00", "13:00"], ["14:00", "20:00"]], // Вт: с перерывом
  "2": [["09:00", "18:00"]],
  "3": [["09:00", "18:00"]],
  "4": [["09:00", "18:00"]],
  "5": [["10:00", "16:00"]],                    // Сб: короткий день
  "6": []                                       // Вс: выходной
}
```

**Ключ** — день недели (0 = Пн, 6 = Вс)
**Значение** — массив интервалов [start, end]

---

## 6. API Endpoints

### 6.1. Получение календаря дней (Level 1)

```
GET /slots/calendar
```

**Query params:**
| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| location_id | int | ✅ | ID локации |
| service_id | int | ❌ | ID услуги (для информации о длительности) |

**Response:**
```json
{
  "location_id": 1,
  "horizon_days": 60,
  "min_advance_hours": 6,
  "service_id": 12,
  "service_duration_min": 60,
  "days": [
    {
      "date": "2025-01-20",
      "weekday": 0,
      "is_available": true,
      "open_slots_count": 24
    },
    {
      "date": "2025-01-21",
      "weekday": 1,
      "is_available": true,
      "open_slots_count": 32
    },
    {
      "date": "2025-01-22",
      "weekday": 2,
      "is_available": false,
      "open_slots_count": 0
    }
  ]
}
```

**Логика:**
- Возвращает `horizon_days` дней начиная с сегодня
- `is_available: true` если есть хотя бы один открытый слот
- Расчёт: Level 1 (базовая сетка локации)

---

### 6.2. Получение слотов дня (Level 2)

```
GET /slots/day
```

**Query params:**
| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| location_id | int | ✅ | ID локации |
| service_id | int | ✅ | ID услуги |
| date | date | ✅ | Выбранный день (YYYY-MM-DD) |

**Response:**
```json
{
  "location_id": 1,
  "service_id": 12,
  "date": "2025-01-20",
  "service_duration_min": 60,
  "slots_needed": 4,
  "available_times": [
    {
      "time": "10:00",
      "slot_index": 40,
      "specialists": [
        {"id": 5, "name": "Иван Петров"},
        {"id": 7, "name": "Мария Сидорова"}
      ]
    },
    {
      "time": "10:15",
      "slot_index": 41,
      "specialists": [
        {"id": 5, "name": "Иван Петров"}
      ]
    },
    {
      "time": "14:00",
      "slot_index": 56,
      "specialists": [
        {"id": 5, "name": "Иван Петров"},
        {"id": 7, "name": "Мария Сидорова"},
        {"id": 12, "name": "Алексей Козлов"}
      ]
    }
  ]
}
```

**Логика:**
- Расчёт: Level 2 (гранулярный)
- `available_times` — слоты, где можно НАЧАТЬ запись
- Для каждого слота — список доступных специалистов

---

### 6.3. Проверка конкретного слота (опционально)

```
GET /slots/check
```

**Query params:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| location_id | int | ID локации |
| service_id | int | ID услуги |
| specialist_id | int | ID специалиста |
| datetime | ISO datetime | Время начала |

**Response (доступен):**
```json
{
  "available": true,
  "location_id": 1,
  "service_id": 12,
  "specialist_id": 5,
  "datetime": "2025-01-20T10:00:00",
  "slots_needed": 4,
  "room_id": 3
}
```

**Response (недоступен):**
```json
{
  "available": false,
  "reason": "specialist_busy",
  "message": "Специалист занят в это время"
}
```

---

### 6.4. Создание бронирования

```
POST /bookings
```

**Body:**
```json
{
  "location_id": 1,
  "service_id": 12,
  "specialist_id": 5,
  "datetime": "2025-01-20T10:00:00",
  "client_id": 100,
  "notes": "Первичный приём"
}
```

**Response (успех):**
```json
{
  "id": 456,
  "location_id": 1,
  "service_id": 12,
  "specialist_id": 5,
  "room_id": 3,
  "client_id": 100,
  "date_start": "2025-01-20T10:00:00",
  "date_end": "2025-01-20T11:00:00",
  "duration_minutes": 60,
  "break_minutes": 15,
  "status": "pending",
  "final_price": 5000.00
}
```

**Response (конфликт):**
```json
{
  "error": "slot_conflict",
  "message": "Выбранное время уже занято",
  "code": 409
}
```

**Внутренняя логика — см. раздел 7.**

---

## 7. Механизм бронирования (Race Condition Protection)

### 7.1. Проблема

Два клиента одновременно пытаются забронировать один слот:
```
Client A: GET /slots/check → available: true
Client B: GET /slots/check → available: true
Client A: POST /bookings → ✅ created
Client B: POST /bookings → ❌ должен получить ошибку!
```

### 7.2. Решение: Redis Lock + Double Check

```
┌─────────────────────────────────────────────────────────────────┐
│                    POST /bookings                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Валидация входных данных                                     │
│    - specialist существует и is_active                          │
│    - service существует и is_active                             │
│    - specialist оказывает service                               │
│    - datetime в пределах 60 дней                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Получить distributed lock                                    │
│    SETNX slots:lock:{specialist_id}:{date} {request_id}         │
│    EXPIRE 30 секунд                                             │
│                                                                 │
│    Если lock не получен → HTTP 409 Conflict                     │
│    "Слот обрабатывается другим запросом"                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Double-check: повторно проверить слоты                       │
│    Пересчитать grid из SQLite (свежие данные)                   │
│                                                                 │
│    Если слот занят → освободить lock → HTTP 409 Conflict        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Создать booking в SQLite                                     │
│    INSERT INTO bookings (...)                                   │
│    Зафиксировать duration_minutes, break_minutes                │
│    Назначить room_id (первая свободная из service_rooms)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Освободить lock                                              │
│    DEL slots:lock:{location_id}:{date}                          │
│                                                                 │
│    (Базовая сетка НЕ инвалидируется — bookings на Level 2)     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Вернуть результат                                            │
│    HTTP 201 Created + booking object                            │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3. Redis Lock Script (Lua)

```lua
-- acquire_lock.lua
local key = KEYS[1]
local value = ARGV[1]
local ttl = ARGV[2]

if redis.call("SETNX", key, value) == 1 then
    redis.call("EXPIRE", key, ttl)
    return 1
end
return 0
```

```lua
-- release_lock.lua
local key = KEYS[1]
local value = ARGV[1]

if redis.call("GET", key) == value then
    return redis.call("DEL", key)
end
return 0
```

---

## 8. Триггеры инвалидации кеша (Level 1)

### 8.1. Когда инвалидировать базовую сетку?

| Событие | Инвалидация | Период |
|---------|-------------|--------|
| Изменение `locations.work_schedule` | ✅ Да | horizon_days |
| Создание `calendar_override` (location) | ✅ Да | affected dates |
| Удаление `calendar_override` (location) | ✅ Да | affected dates |
| Создание `booking` | ❌ **НЕТ** | — |
| Отмена `booking` | ❌ **НЕТ** | — |
| Изменение графика специалиста | ❌ НЕТ | — |
| Изменение комнаты | ❌ НЕТ | — |

**Почему bookings НЕ инвалидируют базовую сетку:**
- Базовая сетка = "локация работает или нет"
- Bookings проверяются на Level 2 (на лету)
- Это даёт стабильный кеш с редкой инвалидацией

### 8.2. Стратегия: Lazy Invalidation

```
1. При изменении schedule/override локации:
   - DEL slots:day:{location_id}:{affected_dates}

2. При запросе /slots/calendar:
   - ZCOUNT для проверки наличия в кеше
   - Если нет → calculate_day_slots() → ZADD в Redis → вернуть
```

### 8.3. Callback для инвалидации

```python
# services/slots/invalidator.py

def invalidate_location_cache(
    redis: Redis,
    location_id: int,
    dates: list[date] | None = None
) -> int:
    """
    Инвалидация базовой сетки локации.

    Args:
        location_id: ID локации
        dates: список дат или None для всего горизонта

    Returns:
        Количество удалённых ключей
    """
    if dates:
        keys = [f"slots:day:{location_id}:{d.isoformat()}" for d in dates]
    else:
        keys = redis.keys(f"slots:day:{location_id}:*")

    if keys:
        return redis.delete(*keys)
    return 0
```

**Использование в роутерах:**

```python
# При изменении work_schedule локации
@router.patch("/locations/{id}")
async def update_location(...):
    # ... update в БД ...
    
    if "work_schedule" in changes:
        await invalidate_location_cache(redis, location_id)
    
    return location

# При создании/удалении override локации
@router.post("/calendar-overrides")
async def create_override(...):
    # ... insert в БД ...
    
    if override.target_type == "location":
        dates = get_affected_dates(override)
        await invalidate_location_cache(redis, override.target_id, dates)
    
    return override
```

---

## 9. Ограничения и граничные случаи

### 9.1. Бизнес-ограничения

| Ограничение | Значение | Источник |
|-------------|----------|----------|
| Мин. время до записи | 1/6/12/24 часа | `config.min_advance_hours` |
| Макс. горизонт записи | 30/60/90 дней | `config.horizon_days` |
| Шаг сетки | 15 мин | Фиксированный |
| Мин. длительность услуги | 15 мин | Service validation |
| Макс. длительность услуги | 480 мин (8ч) | Service validation |
| Одновременных броней на слот | 1 | Lock mechanism |

### 9.2. Граничные случаи

**Бронь на границе дня:**
```
Услуга 90 мин, старт 23:00
→ Занимает 23:00-00:30 следующего дня
→ Нужно заблокировать слоты в ДВУХ днях
```

**Решение:** При создании брони проверять и блокировать оба дня.

**Изменение услуги после брони:**
```
Услуга была 60 мин, клиент записался
Админ изменил на 90 мин
```

**Решение:** `bookings.duration_minutes` фиксируется при создании брони и НЕ меняется.

**Одновременные отмена + запись:**
```
Client A отменяет бронь на 10:00
Client B записывается на 10:00
```

**Решение:** Оба действия используют lock, второй дождётся первого.

---

## 10. Структура файлов (Backend)

```
backend/app/
├── services/
│   └── slots/
│       ├── __init__.py
│       ├── calculator.py      # Алгоритм расчёта grid
│       ├── redis_store.py     # Работа с Redis
│       ├── lock.py            # Distributed lock
│       └── invalidator.py     # Инвалидация кеша
├── routers/
│   └── slots.py               # API endpoints
└── schemas/
    └── slots.py               # Pydantic models
```

---

## 11. Access Policy (Gateway)

Добавить в `policy.json`:

```json
{
  "name": "slots-calendar",
  "path": ["/slots/calendar", "/slots/day", "/slots/check"],
  "methods": ["GET"],
  "allow": ["public", "tg_client", "admin_bot", "internal"]
},
{
  "name": "slots-internal",
  "path": ["/internal/slots/*"],
  "methods": ["POST"],
  "allow": ["internal"]
}
```

---

## 12. Метрики и мониторинг

### 12.1. Ключевые метрики

| Метрика | Описание |
|---------|----------|
| `slots_cache_hit_rate` | % запросов из Redis |
| `slots_calc_duration_ms` | Время расчёта grid |
| `booking_lock_wait_ms` | Время ожидания lock |
| `booking_conflict_rate` | % отклонённых из-за конфликта |

### 12.2. Логирование

```python
logger.info(
    "Slot calculation",
    extra={
        "specialist_id": 5,
        "date": "2025-01-20",
        "duration_ms": 12,
        "cache_hit": False
    }
)
```

---

## 13. Решения и открытые вопросы

### Принятые решения

| # | Вопрос | Решение |
|---|--------|---------|
| 1 | Стратегия расчёта | ✅ **Lazy** — у каждой локации своё расписание |
| 2 | Архитектура | ✅ **Двухуровневая** — Level 1 (локация) + Level 2 (услуга/специалист) |
| 3 | Кеширование | ✅ **Level 1 в Redis**, Level 2 на лету |
| 4 | Конфигурация | ✅ **Настраиваемые**: horizon_days, min_advance_hours |
| 5 | Формат Redis | ✅ **Sorted Set** — (time, expire_ts), автоистечение |
| 6 | Bookings в базовой сетке | ✅ **НЕТ** — bookings только на Level 2 |
| 7 | Комнаты | ✅ Привязаны к УСЛУГЕ (service_rooms), не к специалисту |

### Отложенные решения

| # | Вопрос | Когда решать |
|---|--------|--------------|
| 1 | Room lock (нужен ли отдельный) | При реализации Level 2 |
| 2 | Детализация статусов для UI | По требованиям от фронтенда |

---

## 14. План реализации

### Phase 1: Level 1 — Базовая сетка локации
1. [ ] `BookingConfig` — конфигурация (horizon_days, min_advance_hours)
2. [ ] `calculator.py` — расчёт grid локации (schedule + overrides + min_advance)
3. [ ] `redis_store.py` — чтение/запись в Redis
4. [ ] `GET /slots/calendar` — календарь дней
5. [ ] Lazy caching с TTL
6. [ ] `invalidator.py` — callback для инвалидации кеша

### Phase 2: Level 2 — Гранулярный расчёт
7. [ ] `service_availability.py` — расчёт для услуги
8. [ ] `GET /slots/day` — слоты дня (спецы + комнаты + bookings)
9. [ ] Логика service_rooms (комната нужна / не нужна)

### Phase 3: Бронирование
10. [ ] Lock механизм в `POST /bookings`
11. [ ] Double-check перед созданием (Level 2)
12. [ ] Назначение room_id из пула

### Phase 4: Расширение
13. [ ] `GET /slots/check` — быстрая проверка слота
14. [ ] Метрики и мониторинг

---

```

backend/app/
├── services/
│   └── slots/
│       ├── __init__.py
│       ├── config.py             # BookingConfig
│       ├── calculator.py         # Level 1 (sync)
│       ├── availability.py       # Level 2 (sync)
│       ├── redis_store.py        # Обёртка над redis_client (sync)
│       ├── invalidator.py        # invalidate_location_cache (sync)
│       └── lock.py               # Distributed lock (sync)
│
├── routers/
│   ├── slots.py                  # GET /slots/calendar, GET /slots/day
│   └── ...
│
├── schemas/
│   └── slots.py                  # Pydantic models
│
└── redis_client.py               # Уже есть (sync)

```

## 15. Changelog

| Версия | Дата | Изменения |
|--------|------|-----------|
| 1.0 | 2025-01-19 | Начальная архитектура |
| 1.1 | 2025-01-19 | Двухуровневая архитектура (Level 1: локация, Level 2: услуга). Конфиг UI-ограничений. Lazy-расчёт. UX flow. |
| 1.2 | 2025-01-19 | Capacity planning. Выбран формат Redis: String "0"/"1". MGET оптимизация. |
| 1.3 | 2025-01-19 | Bookings убраны из Level 1. Комнаты привязаны к услуге (service_rooms). |
| 1.4 | 2025-01-19 | Internal API заменён на callback-функцию `invalidate_location_cache()`. |
| 1.5 | 2026-01-30 | **АКТУАЛИЗАЦИЯ:** Формат Redis изменён на Sorted Set (ZSET). Ключ: `slots:day:{loc}:{date}`, значение: `(time_str, expire_ts)`. Автоматическое истечение слотов через ZRANGEBYSCORE. |

