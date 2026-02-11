# План: Веб-интерфейсы для бронирования

## Обзор

Создание двух веб-интерфейсов с единой точкой входа через Gateway:

1. **Standalone Website** (public) — автономный сайт:
   - Главная страница (landing)
   - Страница прайсов (услуги и цены)
   - Страница записи (полный flow с вводом телефона)

2. **PWA / Telegram Mini App** (tg_client):
   - Только страница записи
   - Без ввода телефона (user уже известен из initData)
   - Контент/информация в TG канале

## Архитектура

### Модель безопасности

```
┌─────────────────────────────────────────────────────────┐
│                    UNTRUSTED                            │
│                                                         │
│   Browser (Web UI)                                      │
│           │                                             │
│           ▼                                             │
│       Gateway (8080)                                    │
│           │                                             │
│           ▼                                             │
│   ┌───────────────┐                                     │
│   │  Redis ONLY   │  ← pending_booking:{uuid}          │
│   └───────┬───────┘                                     │
└───────────┼─────────────────────────────────────────────┘
            │
            │ consumer (asyncio task)
            ▼
┌─────────────────────────────────────────────────────────┐
│                    TRUSTED                              │
│                                                         │
│   TG Mini App ──► Gateway ──► Backend API ──► SQLite   │
│        │              │                                 │
│        │         initData                               │
│        │         verified                               │
│        │              │                                 │
│   TG Bot ─────────────┘                                 │
│                                                         │
│   Consumer ──────────► Backend API ──► SQLite          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Два разных flow:**

| Источник | Trust | Путь |
|----------|-------|------|
| Web UI (browser) | ❌ untrusted | Gateway → Redis → Consumer → Backend |
| Mini App (TG) | ✅ trusted (initData) | Gateway → Backend API |
| TG Bot | ✅ trusted | Gateway → Backend API |

**Принцип:** Web UI (public) НЕ имеет доступа к SQL. Только Redis.
- Нельзя выполнить SQL injection
- Нельзя внедрить скрытые инструкции
- Данные валидируются trusted consumer перед записью в SQL

### Поток данных (Web Booking)

```
1. Web UI → POST /web/booking → Gateway
2. Gateway валидирует базово → Redis: pending_booking:{uuid}
3. Gateway возвращает {uuid, status: "pending"}
4. Consumer (trusted) читает Redis → валидирует → Backend API → SQL
5. Consumer обновляет Redis: status → "confirmed" или "failed"
6. Web UI polling GET /web/booking/{uuid} → получает статус
```

### Redis структура для web bookings

**Резерв слота (при выборе времени):**
```
Key: slot_reserve:{location_id}:{date}:{time}:{uuid}
TTL: 5 минут
Value: {uuid}
```

При выборе времени → проверяем нет ли уже резерва → создаём свой.
Если за 5 мин не подтвердил → ключ истекает, слот свободен.

**Pending booking (при подтверждении):**
```
Key: pending_booking:{uuid}
TTL: 5 минут (pending) → 10 минут (confirmed, для polling)
Value: {
    "service_id": 1,
    "specialist_id": 2,
    "date": "2024-02-10",
    "time": "10:00",
    "phone": "+79991234567",
    "name": "Имя",
    "status": "pending",       # pending → processing → confirmed/failed
    "error": null,
    "booking_id": null,
    "created_at": "2024-02-10 09:30:00"
}
```

**Flow:**
```
1. Услуга → День → Время
2. POST /web/reserve → slot_reserve:{...} (TTL 5 min)
3. Клиент вводит телефон, имя
4. POST /web/booking → pending_booking:{uuid}
5. Consumer → SQL → status: confirmed
6. Удаляем slot_reserve, обновляем Level 1 cache
```

### Web API endpoints (Gateway, не проксируются в Backend)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| GET /web/services | GET | Список услуг (из Redis cache) |
| GET /web/slots/calendar | GET | Доступные дни (из Redis cache) |
| GET /web/slots/day | GET | Слоты на день (с учётом резервов) |
| POST /web/reserve | POST | Резерв слота (TTL 5 min) |
| DELETE /web/reserve/{uuid} | DELETE | Отмена резерва |
| POST /web/booking | POST | Подтверждение → pending booking |
| GET /web/booking/{uuid} | GET | Статус booking |

**Важно:** Эти endpoints обрабатываются Gateway напрямую, БЕЗ проксирования в Backend.

### Consumer (trusted)

Работает как asyncio task в Gateway (аналогично p2p_consumer, broadcast_consumer):

```python
# gateway/app/events/web_booking_consumer.py
async def web_booking_consumer():
    """Обрабатывает pending bookings из Redis → SQL"""
    while True:
        # Сканируем pending_booking:* с status=pending
        # Валидируем данные (service exists, slot available, etc)
        # Создаём booking через internal Backend API call
        # Обновляем статус в Redis
        await asyncio.sleep(1)
```

### Кеширование справочников

Справочники в Redis **без TTL** — перезаписываются при изменении:

```
cache:services      → Backend пишет при CRUD /services
cache:specialists   → Backend пишет при CRUD /specialists
cache:locations     → Backend пишет при CRUD /locations
```

**Backend при update:**
```python
# backend/app/routers/services.py
@router.put("/{id}")
async def update_service(...):
    # ... update in SQL
    await redis.set("cache:services", json.dumps(all_services))
```

Слоты (Level 1) остаются с TTL — они зависят от расписания и bookings.

Web UI читает ТОЛЬКО из Redis cache, не из SQL.

## Структура Frontend

```
frontend/
├── index.html            # Landing page (статика, SEO)
├── pricing.html          # Прайс-лист (статика, SEO)
├── book.html             # Страница записи
├── miniapp.html          # TG Mini App
│
├── ts/
│   ├── api.ts            # API client (fetch wrapper)
│   ├── booking.ts        # Booking wizard logic
│   ├── miniapp.ts        # Mini App logic
│   └── pricing.ts        # Загрузка прайса (опционально)
│
├── dist/
│   ├── bundle.js         # Скомпилированный TS
│   └── bundle.js.map     # Source maps
│
├── css/
│   └── styles.css        # Custom styles (поверх Tailwind)
│
├── images/
│   └── logo.svg
│
└── tsconfig.json         # TypeScript конфиг
```

### TypeScript Build

```bash
# Одноразовая компиляция
tsc

# Watch mode для разработки
tsc --watch
```

**tsconfig.json:**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ES2020",
    "outDir": "./dist",
    "rootDir": "./ts",
    "strict": true,
    "esModuleInterop": true,
    "sourceMap": true
  },
  "include": ["ts/**/*"]
}
```

### Страницы

| URL | Файл | Описание |
|-----|------|----------|
| / | index.html | Landing page (статический контент для SEO) |
| /pricing | pricing.html | Прайс-лист (услуги загружаются через JS) |
| /book | book.html | Booking wizard |
| /miniapp | miniapp.html | TG Mini App |

Все страницы — **статические HTML**. Данные загружаются через fetch API.

### SEO подход

Для SEO важно что:
- HTML файлы содержат базовый контент (заголовки, описания)
- meta tags присутствуют в HTML
- Динамические данные (услуги, слоты) загружаются после рендера

```html
<!-- index.html - базовая структура -->
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Онлайн запись на услуги">
    <title>Салон красоты - Онлайн запись</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="/css/styles.css">
</head>
<body>
    <!-- Статический контент для SEO -->
    <header>...</header>
    <main>...</main>
    <footer>...</footer>

    <script type="module" src="/dist/bundle.js"></script>
</body>
</html>
```

## Booking Flow

### Website (public) — через Redis

```
1. GET /web/services         ← из Redis cache
       ▼
2. GET /web/slots/calendar   ← доступные дни
       ▼
3. GET /web/slots/day        ← слоты (с учётом резервов)
       ▼
4. POST /web/reserve         ← РЕЗЕРВ слота (TTL 5 min)
       ▼
5. Ввод телефона + имя (5 мин на заполнение)
       ▼
6. POST /web/booking         ← подтверждение → pending
       ▼
7. Polling GET /web/booking/{uuid}
       ▼
   [Consumer: Redis → SQL, удаляет резерв]
```

### Mini App (tg_client) — через Backend API

Mini App остаётся trusted (initData верифицируется):
```
1. GET /services            ← через Gateway → Backend
       ▼
2. GET /specialists
       ▼
3. GET /slots/calendar
       ▼
4. GET /slots/day
       ▼
5. POST /bookings           ← client_id из initData
```

## Изменения Backend

### Internal endpoint для consumer (trusted only)

**POST /internal/bookings/from-web**
```python
class WebBookingCreate(BaseModel):
    service_id: int
    specialist_id: int | None = None
    date: str
    time: str
    phone: str
    name: str | None = None

@router.post("/internal/bookings/from-web")
async def create_booking_from_web(data: WebBookingCreate):
    # 1. Валидация: service exists, slot available
    # 2. Найти или создать user по phone
    # 3. Создать booking
    return {"booking_id": ..., "client_id": ...}
```

Доступ: только localhost / internal token (не через Gateway proxy).

## Изменения Gateway

### 1. Static Files setup

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/dist", StaticFiles(directory="frontend/dist"), name="dist")
app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
app.mount("/images", StaticFiles(directory="frontend/images"), name="images")
```

### 2. HTML routes

```python
@app.get("/")
async def serve_home():
    return FileResponse("frontend/index.html")

@app.get("/book")
async def serve_booking():
    return FileResponse("frontend/book.html")

@app.get("/miniapp")
async def serve_miniapp():
    return FileResponse("frontend/miniapp.html")
```

### 3. Web API routes (Redis only, no SQL)

```python
# gateway/app/routers/web_booking.py

@router.get("/web/services")
async def get_services(redis: Redis):
    """Возвращает услуги из Redis cache"""
    cached = await redis.get("cache:services")
    if cached:
        return json.loads(cached)
    # Cache miss → запрос к Backend, кеширование
    ...

@router.get("/web/slots/calendar")
async def get_calendar(service_id: int, redis: Redis):
    """Доступные дни из Redis Level 1 cache"""
    ...

@router.get("/web/slots/day")
async def get_day_slots(date: str, service_id: int, redis: Redis):
    """Слоты на день из Redis"""
    ...

@router.post("/web/booking")
async def create_pending_booking(data: WebBookingRequest, redis: Redis):
    """Создаёт pending booking в Redis"""
    uuid = str(uuid4())
    await redis.setex(
        f"pending_booking:{uuid}",
        3600,  # TTL 1 hour
        json.dumps({
            "service_id": data.service_id,
            "specialist_id": data.specialist_id,
            "date": data.date,
            "time": data.time,
            "phone": data.phone,
            "name": data.name,
            "status": "pending",
            "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        })
    )
    return {"uuid": uuid, "status": "pending"}

@router.get("/web/booking/{uuid}")
async def get_booking_status(uuid: str, redis: Redis):
    """Статус pending booking"""
    data = await redis.get(f"pending_booking:{uuid}")
    if not data:
        raise HTTPException(404, "Booking not found")
    return json.loads(data)
```

### 4. Web Booking Consumer (asyncio task)

```python
# gateway/app/events/web_booking_consumer.py

async def web_booking_consumer(redis: Redis, backend_client: httpx.AsyncClient):
    """Обрабатывает pending bookings: Redis → SQL"""
    while True:
        # Сканируем ключи pending_booking:*
        keys = await redis.keys("pending_booking:*")
        for key in keys:
            data = json.loads(await redis.get(key))
            if data["status"] != "pending":
                continue

            # Помечаем как processing
            data["status"] = "processing"
            await redis.setex(key, 3600, json.dumps(data))

            try:
                # Вызов trusted Backend API
                resp = await backend_client.post(
                    "http://127.0.0.1:8000/internal/bookings/from-web",
                    json=data
                )
                result = resp.json()

                data["status"] = "confirmed"
                data["booking_id"] = result["booking_id"]
            except Exception as e:
                data["status"] = "failed"
                data["error"] = str(e)

            await redis.setex(key, 3600, json.dumps(data))

        await asyncio.sleep(1)
```

## Технологии Frontend

- **Статические HTML** — все страницы (SEO-friendly)
- **TypeScript** — компилируется в bundle.js через `tsc`
- **TailwindCSS CDN** (Play CDN, без build step)
- **Telegram Web App SDK** для Mini App

**Без node_modules/npm** — только `tsc` для компиляции TypeScript.

## Примеры кода

### ts/api.ts
```typescript
export interface Service {
  id: number;
  name: string;
  duration: number;
  price: number;
}

export interface TimeSlot {
  time: string;
  available: boolean;
}

export interface PendingBooking {
  uuid: string;
  status: 'pending' | 'processing' | 'confirmed' | 'failed';
  booking_id?: number;
  error?: string;
}

export class BookingAPI {
  // Web UI использует /web/* endpoints (Redis only)
  private baseUrl = '/web';

  async getServices(): Promise<Service[]> {
    const response = await fetch(`${this.baseUrl}/services`);
    return response.json();
  }

  async getAvailableDays(serviceId: number, specialistId?: number): Promise<string[]> {
    const params = new URLSearchParams({ service_id: String(serviceId) });
    if (specialistId) params.append('specialist_id', String(specialistId));
    const response = await fetch(`${this.baseUrl}/slots/calendar?${params}`);
    return response.json();
  }

  async getTimeSlots(date: string, serviceId: number): Promise<TimeSlot[]> {
    const response = await fetch(`${this.baseUrl}/slots/day?date=${date}&service_id=${serviceId}`);
    return response.json();
  }

  async createBooking(data: {
    service_id: number;
    specialist_id?: number;
    date: string;
    time: string;
    phone: string;
    name?: string;
  }): Promise<{ uuid: string; status: string }> {
    const response = await fetch(`${this.baseUrl}/booking`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return response.json();
  }

  async getBookingStatus(uuid: string): Promise<PendingBooking> {
    const response = await fetch(`${this.baseUrl}/booking/${uuid}`);
    return response.json();
  }

  // Polling до confirmed/failed
  async waitForConfirmation(uuid: string, maxAttempts = 30): Promise<PendingBooking> {
    for (let i = 0; i < maxAttempts; i++) {
      const status = await this.getBookingStatus(uuid);
      if (status.status === 'confirmed' || status.status === 'failed') {
        return status;
      }
      await new Promise(r => setTimeout(r, 1000));
    }
    throw new Error('Timeout waiting for confirmation');
  }
}
```

### ts/booking.ts
```typescript
import { BookingAPI, Service } from './api.js';

type Step = 'service' | 'specialist' | 'calendar' | 'time' | 'phone' | 'confirm';

class BookingApp {
  private api = new BookingAPI();
  private currentStep: Step = 'service';

  private selectedService: Service | null = null;
  private selectedSpecialistId: number | null = null;
  private selectedDate: string = '';
  private selectedTime: string = '';
  private phone: string = '';

  constructor() {
    this.initEventListeners();
    this.loadServices();
  }

  private async loadServices(): Promise<void> {
    const services = await this.api.getServices();
    this.renderServices(services);
  }

  private renderServices(services: Service[]): void {
    const container = document.getElementById('services-list');
    if (!container) return;

    container.innerHTML = services.map(s => `
      <button class="service-btn" data-id="${s.id}">
        ${s.name} — ${s.price}₽
      </button>
    `).join('');
  }

  private showStep(step: Step): void {
    document.querySelectorAll('.step').forEach(el => el.classList.remove('active'));
    document.getElementById(`step-${step}`)?.classList.add('active');
    this.currentStep = step;
  }

  private initEventListeners(): void {
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      if (target.classList.contains('service-btn')) {
        const id = Number(target.dataset.id);
        // ... handle service selection
        this.showStep('calendar');
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => new BookingApp());
```

### book.html (структура)
```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Запись онлайн</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="/css/styles.css">
</head>
<body class="bg-gray-50">
    <div id="booking-app" class="max-w-md mx-auto p-4">

        <div id="step-service" class="step active">
            <h2 class="text-xl font-bold mb-4">Выберите услугу</h2>
            <div id="services-list" class="space-y-2"></div>
        </div>

        <div id="step-specialist" class="step hidden">
            <h2 class="text-xl font-bold mb-4">Выберите специалиста</h2>
            <div id="specialists-list" class="space-y-2"></div>
            <button id="skip-specialist" class="text-gray-500">Любой специалист</button>
        </div>

        <div id="step-calendar" class="step hidden">
            <h2 class="text-xl font-bold mb-4">Выберите дату</h2>
            <div id="calendar" class="grid grid-cols-7 gap-1"></div>
        </div>

        <div id="step-time" class="step hidden">
            <h2 class="text-xl font-bold mb-4">Выберите время</h2>
            <div id="time-slots" class="grid grid-cols-4 gap-2"></div>
        </div>

        <div id="step-phone" class="step hidden">
            <h2 class="text-xl font-bold mb-4">Ваш телефон</h2>
            <input type="tel" id="phone-input" class="w-full p-3 border rounded" placeholder="+7">
            <button id="phone-submit" class="w-full mt-4 bg-blue-500 text-white p-3 rounded">
                Продолжить
            </button>
        </div>

        <div id="step-confirm" class="step hidden">
            <h2 class="text-xl font-bold mb-4">Подтверждение</h2>
            <div id="booking-summary" class="bg-white p-4 rounded shadow"></div>
            <button id="confirm-btn" class="w-full mt-4 bg-green-500 text-white p-3 rounded">
                Записаться
            </button>
        </div>

    </div>
    <script type="module" src="/dist/booking.js"></script>
</body>
</html>
```

## Контент-менеджмент через TG канал (Этап 7 — отложено)

*Будет реализован после базового booking flow.*

Коротко: посты из закрытого TG канала сохраняются в БД → отображаются на сайте.

## Файлы для изменения/создания

### Gateway (основные изменения)
| Путь | Описание |
|------|----------|
| `gateway/app/main.py` | Static files mount + HTML routes |
| `gateway/app/routers/web_booking.py` | **НОВЫЙ** — Web API endpoints (/web/*) |
| `gateway/app/events/web_booking_consumer.py` | **НОВЫЙ** — Consumer: Redis → SQL |

### Backend
| Путь | Описание |
|------|----------|
| `backend/app/routers/internal.py` | **НОВЫЙ** — POST /internal/bookings/from-web |

### Frontend (новая директория)
| Путь | Описание |
|------|----------|
| `frontend/index.html` | Landing page |
| `frontend/book.html` | Страница записи |
| `frontend/miniapp.html` | TG Mini App |
| `frontend/ts/api.ts` | API client (/web/* endpoints) |
| `frontend/ts/booking.ts` | BookingApp class |
| `frontend/ts/miniapp.ts` | Mini App logic |
| `frontend/css/styles.css` | Custom styles |
| `frontend/tsconfig.json` | TypeScript конфиг |

## Этапы реализации

### Этап 1: Gateway — Web API routes
1. `gateway/app/routers/web_booking.py` — /web/* endpoints (Redis only)
2. GET /web/services, /web/slots/* — из Redis cache
3. POST /web/booking — создаёт pending в Redis
4. GET /web/booking/{uuid} — статус

### Этап 2: Gateway — Consumer
1. `gateway/app/events/web_booking_consumer.py`
2. Читает pending_booking:* из Redis
3. Вызывает Backend internal API
4. Обновляет статус в Redis

### Этап 3: Backend — Internal endpoint
1. POST /internal/bookings/from-web
2. Валидация, создание user по phone, создание booking
3. Доступ только localhost

### Этап 4: Gateway — Static Files
1. Static files mount для frontend/
2. HTML routes: /, /book, /miniapp

### Этап 5: Frontend — TypeScript
1. tsconfig.json
2. ts/api.ts — /web/* endpoints + polling
3. Компиляция: `tsc`

### Этап 6: Frontend — Booking UI
1. book.html — wizard UI
2. ts/booking.ts — step machine, валидация

### Этап 7: Mini App (отдельный flow)
1. miniapp.html + ts/miniapp.ts
2. TG Web App SDK
3. Использует /api/* (trusted через initData)

### Этап 8: Контент-менеджмент (отложено)

## Верификация

1. **Security check:**
   - Web UI НЕ имеет доступа к /api/* (Backend)
   - Web UI работает ТОЛЬКО через /web/* (Redis)
   - Consumer работает на localhost (trusted)

2. **Website flow:**
   - POST /web/booking → pending в Redis
   - Consumer обрабатывает → SQL
   - GET /web/booking/{uuid} → confirmed

3. **Mini App flow:**
   - initData верификация
   - Прямой доступ к /api/* через Gateway
   - POST /bookings с client_id

4. **Redis keys:**
   - `pending_booking:{uuid}` — TTL 1h
   - `cache:services` — TTL 5min
