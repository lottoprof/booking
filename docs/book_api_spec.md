# book.html — ТЗ по API-интеграции

## Проблема

После перехода на `PricingCard` формат (`GET /web/services`) фронтенд `book.html` сломан:
старый формат имел `id`, `price`, `duration_max` — в новом их нет.

---

## 1. GET /web/services (view=booking)

### Что возвращает сейчас (PricingCard)

```json
{
  "name": "LPG",
  "slug": "lpg",
  "description": "по костюму",
  "category": "body",
  "icon": "✦",
  "duration_min": 45,
  "variants": [
    { "label": "Разовый сеанс", "qty": 1, "price": 1800.0, "old_price": null, "per_session": null }
  ]
}
```

### Чего не хватает для букинга

| Поле | Зачем |
|------|-------|
| `package_id` | Передать в `POST /web/reserve` → `service_package_id` |
| `service_ids` | Передать в `GET /web/slots/day` → `service_id` (для одиночных) |

### Решение: добавить в `ServiceVariant`

```python
class ServiceVariant(BaseModel):
    package_id: int          # ← NEW: service_packages.id
    label: str
    qty: int = 1
    price: float
    old_price: Optional[float] = None
    per_session: Optional[float] = None
```

И в `PricingCard`:

```python
class PricingCard(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    category: Optional[str] = None
    icon: str = "✦"
    duration_min: int
    service_ids: list[int] = []   # ← NEW: из package_items первого пакета
    variants: list[ServiceVariant] = []
```

---

## 2. Флоу букинга — какие endpoint вызывать

### Шаг 1: Выбор услуги

```
GET /web/services              (без view → show_on_booking=1, только qty=1)
```

Фронтенд показывает карточки. При клике на карточку сохраняет:
- `card.name`, `card.slug`, `card.duration_min`
- `card.variants[0].price` — цена разового сеанса
- `card.variants[0].package_id` — ID пакета для резерва
- `card.service_ids[0]` — service_id для слотов (одиночная услуга)

### Шаг 2: Выбор даты (календарь)

**Сейчас**: календарь рендерится без проверки доступности (все даты кликабельны).

**Нужно**: использовать `GET /web/slots/calendar` для подсветки дней.

```
GET /web/slots/calendar?location_id=1&service_id={service_ids[0]}
                       &start_date=2026-02-01&end_date=2026-03-31
```

Ответ:
```json
{
  "location_id": 1,
  "days": [
    { "date": "2026-02-14", "has_slots": true, "open_slots_count": 12 },
    { "date": "2026-02-15", "has_slots": false, "open_slots_count": 0 }
  ]
}
```

Применение:
- `has_slots: false` → `.cal-day.disabled`
- `has_slots: true` → кликабельный, можно показать точку-индикатор
- Вызывать при каждой смене месяца (`navMonth`)

### Шаг 3: Выбор времени

```
GET /web/slots/day?location_id=1&service_id={service_ids[0]}&date=2026-02-14
```

Без изменений. Ответ — массив `{ time, available, specialists[] }`.

### Шаг 4: Выбор специалиста

```
GET /web/specialists?service_id={service_ids[0]}
```

Без изменений.

### Шаг 5: Резерв слота (5 мин)

```
POST /web/reserve
{
  "location_id": 1,
  "service_package_id": {package_id},   ← из variants[0].package_id
  "specialist_id": 3,                    ← или null
  "date": "2026-02-14",
  "time": "14:00"
}
```

**Изменение**: отправлять `service_package_id` вместо `service_id`.
Endpoint уже принимает оба поля — менять gateway не нужно.

### Шаг 6: Отправка букинга

```
POST /web/booking
{ "reserve_uuid": "...", "phone": "79...", "name": "Имя" }
```

Без изменений.

### Шаг 7: Поллинг статуса

```
GET /web/booking/{uuid}
```

Без изменений.

---

## 3. Что сломано в текущем book.html (конкретные строки)

| Строка | Код | Проблема |
|--------|-----|----------|
| 1028 | `s.id` | PricingCard не имеет `id` → использовать `variants[0].package_id` |
| 1032 | `s.duration_max` | Нет такого поля → убрать или использовать `s.duration_min` |
| 1034 | `s.price` | Нет на уровне карточки → `s.variants[0].price` |
| 1081 | `s.duration_max` | То же |
| 1183 | `this.state.service.id` | → первый `service_ids[0]` или достать из пакета |
| 1237 | `this.state.service.id` | То же |
| 1328 | `this.state.service.price` | → `this.state.service.variants[0].price` |
| 1336 | `service_id` в reserveSlot | → передавать `service_package_id` |
| 870-881 | `BookingAPI.reserveSlot` | Отправляет `service_id` → заменить на `service_package_id` |

---

## 4. Что нужно доделать в бэкенде

| Задача | Файл |
|--------|------|
| Добавить `package_id` в `ServiceVariant` | `backend/app/schemas/services.py` |
| Добавить `service_ids` в `PricingCard` | `backend/app/schemas/services.py` |
| Заполнять эти поля в endpoint | `backend/app/routers/services.py` |

---

## 5. Итого: порядок работы

1. **Backend**: добавить `package_id` и `service_ids` в схемы + endpoint
2. **Frontend** (book.html):
   - `BookingAPI.getServices()` → адаптировать к PricingCard
   - `loadServices()` → читать `card.variants[0].price`, убрать `duration_max`
   - `prepareCalendar()` → вызывать `/web/slots/calendar`, подсвечивать дни
   - `BookingAPI.reserveSlot()` → отправлять `service_package_id`
   - `renderSummary()` → цена из `variants[0].price`
