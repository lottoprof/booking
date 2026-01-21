
# 1. Company

### GET /company  
### GET /company/{id}  
### POST /company  

### PATCH /company/{id}  
Допустимые поля: `name`, `description`

❌ DELETE — запрещён → **405 Method Not Allowed**

---

# 2. Locations

Работают через soft-delete (`is_active=false`).

### GET /locations  
— только активные

### GET /locations/{id}  

### POST /locations  

### PATCH /locations/{id}  
Допустимые поля:  
`is_active`, `name`, `city`, `street`, `house`, `work_schedule`, `notes`

### DELETE /locations/{id}

---

# 3. Rooms

Работают через soft-delete (`is_active=false`).

### GET /rooms  
### GET /rooms/{id}  
### POST /rooms  

### PATCH /rooms/{id}  
Допустимые поля: `is_active`, `name`, `display_order`, `notes`

### DELETE /rooms/{id}

---

# 4. Roles

### GET /roles  
### GET /roles/{id}

❌ PATCH — запрещён → **405 Method Not Allowed**  
❌ DELETE — запрещён → **405 Method Not Allowed**

---

# 5. Users

Работают через soft-delete (`is_active=false`).

### GET /users  
### GET /users/{id}  
### POST /users  

### PATCH /users/{id}  
Допустимые поля:  
`is_active`,  
`first_name`,  
`last_name`,  
`middle_name`,  
`phone`,  
`email`,  
`notes`

### DELETE /users/{id}

---

# 6. User Roles

### GET /user_roles  
### GET /user_roles/{id}  
### POST /user_roles  

❌ PATCH — запрещён → **405 Method Not Allowed**  
(смена роли = DELETE + POST)

### DELETE /user_roles/{id}

---

# 7. Services

Работают через soft-delete (`is_active=false`).

### GET /services  
### GET /services/{id}  
### POST /services  

### PATCH /services/{id}  
Допустимые поля:  
`is_active`, `name`, `description`, `category`, `price`, `color_code`, `duration_min`, `break_min`

### DELETE /services/{id}

---

# 8. Service Packages

Работают через soft-delete (`is_active=false`).

### GET /service_packages  
### GET /service_packages/{id}  
### POST /service_packages  

### PATCH /service_packages/{id}  
Допустимые поля:  
`is_active`, `name`, `description`, `package_items`, `package_price`

### DELETE /service_packages/{id}

---

# 9. Service Rooms

Работают через soft-delete (`is_active=false`).

### GET /service_rooms  
### GET /service_rooms/{id}  
### POST /service_rooms  

### PATCH /service_rooms/{id}  
Допустимые поля: `is_active`, `notes`

### DELETE /service_rooms/{id}

---
# 10. Specialists

Работают через soft-delete (`is_active=false`).

### GET /specialists  
### GET /specialists/{id}  
### POST /specialists  

### PATCH /specialists/{id}  
Допустимые поля:  
`is_active`, `display_name`, `description`, `photo_url`, `work_schedule`

### DELETE /specialists/{id}

---

# 11. Specialist → Services (Domain relation)

Связь «специалист → услуги» является **доменной**, отдельной сущностью не является.  
Таблица `specialist_services` — link-table с составным ключом  
(`specialist_id`, `service_id`) и бизнес-атрибутами.

Отдельного CRUD-ресурса **не существует**.

### GET /specialists/{id}/services  
Список услуг специалиста (только `is_active = true`).

### POST /specialists/{id}/services  
Добавление услуги специалисту.  
Тело запроса:
- `service_id`
- `is_default` (опционально)
- `notes` (опционально)

### PATCH /specialists/{id}/services/{service_id}  
Допустимые поля:  
`is_active`, `is_default`, `notes`

### DELETE /specialists/{id}/services/{service_id}  
Soft-delete связи (`is_active = false`).

---

# 12. Calendar Overrides

### GET /calendar_overrides  
### GET /calendar_overrides/{id}  
### POST /calendar_overrides  

❌ PATCH — запрещён → **405 Method Not Allowed**  
(изменение = DELETE + POST)

### DELETE /calendar_overrides/{id}

---

# 13. Bookings

Историческая сущность. Удаление запрещено для сохранения истории.

### GET /bookings  

Query параметры (фильтрация):
| Параметр | Тип | Описание |
|----------|-----|----------|
| `client_id` | int | Фильтр по клиенту |
| `location_id` | int | Фильтр по локации |
| `specialist_id` | int | Фильтр по специалисту |
| `status` | str | Фильтр по статусу (pending, confirmed, cancelled, done) |
| `date` | str | Точная дата (YYYY-MM-DD) |
| `date_from` | str | date_start >= date_from |
| `date_to` | str | date_start <= date_to |

### GET /bookings/{id}  

### POST /bookings  

Тело запроса (BookingCreate):
```json
{
  "company_id": 1,
  "location_id": 1,
  "service_id": 1,
  "specialist_id": 1,
  "client_id": 1,
  "date_start": "2026-01-21T10:00:00",
  "date_end": "2026-01-21T11:00:00",
  "duration_minutes": 60,
  "break_minutes": 0,
  "room_id": null,
  "notes": null
}
```

### PATCH /bookings/{id}  

Допустимые поля (только admin):
| Поле | Тип | Описание |
|------|-----|----------|
| `date_start` | datetime | Новая дата/время начала |
| `date_end` | datetime | Новая дата/время окончания |
| `specialist_id` | int | Новый специалист |
| `service_id` | int | Новая услуга |
| `duration_minutes` | int | Новая длительность |
| `final_price` | float | Новая цена |
| `room_id` | int | Новая комната |
| `status` | str | Новый статус |
| `cancel_reason` | str | Причина отмены |
| `notes` | str | Заметки |

> Автоматически обновляется `updated_at`.

❌ DELETE — запрещён → **405 Method Not Allowed**  
(используйте `PATCH {status: "cancelled"}` для отмены)

---

# 14. Client Packages

### GET /client_packages  
### GET /client_packages/{id}  
### POST /client_packages  

❌ PATCH — запрещён → **405 Method Not Allowed**

### DELETE /client_packages/{id}

---

# 15. Client Discounts

### GET /client_discounts  
### GET /client_discounts/{id}  
### POST /client_discounts  

### PATCH /client_discounts/{id}  
Допустимые поля: `discount_percent`, `valid_to`, `description`

### DELETE /client_discounts/{id}

---

# 16. Booking Discounts

### GET /booking_discounts  
### GET /booking_discounts/{id}  
### POST /booking_discounts  

❌ PATCH — запрещён → **405 Method Not Allowed**

### DELETE /booking_discounts/{id}

---

---
# 17. Client Wallets (read-only)

Кошелёк — финансовая сущность.  
Любые изменения баланса выполняются **ТОЛЬКО через domain-API кошелька**.

### GET /client_wallets  
### GET /client_wallets/{id}

❌ POST — запрещён → **405 Method Not Allowed**  
❌ PATCH — запрещён → **405 Method Not Allowed**  
❌ DELETE — запрещён → **405 Method Not Allowed**

> Поле `is_blocked` изменяется только системой / админ-логикой  
> и не доступно через публичный CRUD.

---

# 18. Wallet (Domain API)

Domain-API для работы с балансом клиента.  
Все операции фиксируются в `wallet_transactions`.

### GET /wallets/{user_id}  
Текущий кошелёк клиента (баланс, валюта, статус).

### GET /wallets/{user_id}/transactions  
История операций клиента.

### POST /wallets/{user_id}/deposit  
Пополнение кошелька.

### POST /wallets/{user_id}/withdraw  
Ручное списание средств.

### POST /wallets/{user_id}/payment  
Оплата записи / услуги.

### POST /wallets/{user_id}/refund  
Возврат средств клиенту.

### POST /wallets/{user_id}/correction  
Корректировка баланса (только админ / система).

---

# 19. Wallet Transactions (read-only)

Прямой CRUD недоступен.  
Таблица используется **только** как журнал domain-операций.

### GET /wallet_transactions  
### GET /wallet_transactions/{id}

❌ POST — запрещён → **405 Method Not Allowed**  
❌ PATCH — запрещён → **405 Method Not Allowed**  
❌ DELETE — запрещён → **405 Method Not Allowed**

---

# 19. Push Subscriptions

### GET /push_subscriptions  
### GET /push_subscriptions/{id}  
### POST /push_subscriptions  

❌ PATCH — запрещён → **405 Method Not Allowed**

### DELETE /push_subscriptions/{id}

---

# 20. Schema Migrations

❌ Все методы API запрещены → **405 Method Not Allowed**

---

# Backend Endpoints для модуля "Клиенты"

## Реализованные endpoints

### 1. GET /users/search 

Поиск пользователей по телефону, имени, фамилии.

```python
# Пример использования в боте
users = await api.search_users("Иван", limit=20)
```

**Query параметры:**
- `q` (required, min 2 chars) — поисковый запрос
- `limit` (default: 20, max: 100) — макс. количество результатов

**Response:** `list[UserRead]`

---

### 2. GET /users/{id}/stats 

Статистика записей клиента.

```python
stats = await api.get_user_stats(user_id=123)
# {
#   "user_id": 123,
#   "total_bookings": 15,
#   "active_bookings": 2,
#   "completed_bookings": 12,
#   "cancelled_bookings": 1
# }
```

---

### 3. GET /users/{id}/active-bookings` 

Активные записи клиента (pending, confirmed).

```python
bookings = await api.get_user_active_bookings(user_id=123)
```

**Response:** `list[BookingRead]`

---

### 4. PATCH /users/{id}/role 

Смена роли пользователя.

```python
result = await api.change_user_role(user_id=123, role="specialist")
# {
#   "user_id": 123,
#   "old_role": "client",
#   "new_role": "specialist"
# }
```

**Request body:**
```json
{
  "role": "specialist"  // "client" | "specialist" | "manager"
}
```

**Role IDs:**
- admin = 1
- manager = 2
- specialist = 3
- client = 4

---

## Важные детали реализации

1. **Route ordering в users.py**: `/search` размещён ПЕРЕД `/{id}` чтобы избежать конфликта роутов

2. **Date filters**: Используют SQLite `date()` функцию для корректного сравнения дат в TEXT формате

3. **Role change**: Обновляет существующую запись в `user_roles` или создаёт новую

4. **updated_at**: Автоматически обновляется при PATCH bookings

5. **DELETE bookings**: Остаётся заблокированным (405) — используйте PATCH для отмены

# 18. Wallet (Domain API)

Domain-API для работы с балансом клиента.
Все операции фиксируются в `wallet_transactions`.

---

### GET /wallets/{user_id}

Получить кошелёк клиента. Создаёт автоматически с `balance=0` если не существует.

**Response:** `WalletRead`
```json
{
  "id": 1,
  "user_id": 123,
  "balance": 1500.0,
  "currency": "RUB",
  "is_blocked": false
}
```

---

### GET /wallets/{user_id}/transactions

История операций клиента (ORDER BY `created_at DESC`).

**Query параметры:**
| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `limit` | int | 50 | Макс. записей (1-200) |
| `offset` | int | 0 | Смещение |

**Response:** `list[WalletTransactionRead]`
```json
[
  {
    "id": 42,
    "wallet_id": 1,
    "booking_id": 456,
    "amount": -1000.0,
    "type": "payment",
    "description": null,
    "created_by": null,
    "created_at": "2026-01-21T10:30:00"
  }
]
```

---

### POST /wallets/{user_id}/deposit

Пополнение кошелька.

**Request body:** `WalletDeposit`
```json
{
  "amount": 500.0,
  "description": "Наличные",
  "created_by": 1
}
```

| Поле | Тип | Required | Описание |
|------|-----|----------|----------|
| `amount` | float | ✓ | Сумма (> 0) |
| `description` | str | | Комментарий |
| `created_by` | int | | ID оператора |

**Response:** `WalletOperationResponse`

---

### POST /wallets/{user_id}/withdraw

Ручное списание средств.

**Request body:** `WalletWithdraw`
```json
{
  "amount": 200.0,
  "description": "Выдача наличных",
  "created_by": 1
}
```

| Поле | Тип | Required | Описание |
|------|-----|----------|----------|
| `amount` | float | ✓ | Сумма (> 0) |
| `description` | str | | Комментарий |
| `created_by` | int | | ID оператора |

**Ошибки:** `400` — недостаточно средств

---

### POST /wallets/{user_id}/payment

Оплата записи / услуги.

**Request body:** `WalletPayment`
```json
{
  "amount": 1000.0,
  "booking_id": 456,
  "description": "Оплата маникюра"
}
```

| Поле | Тип | Required | Описание |
|------|-----|----------|----------|
| `amount` | float | ✓ | Сумма (> 0) |
| `booking_id` | int | ✓ | ID записи |
| `description` | str | | Комментарий |

**Ошибки:**
- `400` — недостаточно средств
- `404` — запись не найдена

---

### POST /wallets/{user_id}/refund

Возврат средств клиенту.

**Request body:** `WalletRefund`
```json
{
  "amount": 500.0,
  "booking_id": 456,
  "description": "Возврат за отмену",
  "created_by": 1
}
```

| Поле | Тип | Required | Описание |
|------|-----|----------|----------|
| `amount` | float | ✓ | Сумма (> 0) |
| `booking_id` | int | | ID записи (опционально) |
| `description` | str | | Комментарий |
| `created_by` | int | | ID оператора |

---

### POST /wallets/{user_id}/correction

Корректировка баланса (только админ / система).

**Request body:** `WalletCorrection`
```json
{
  "amount": -100.0,
  "description": "Штраф за неявку",
  "created_by": 1
}
```

| Поле | Тип | Required | Описание |
|------|-----|----------|----------|
| `amount` | float | ✓ | Сумма (+ или -) |
| `description` | str | ✓ | Причина (мин. 3 символа) |
| `created_by` | int | ✓ | ID админа |

**Ошибки:** `400` — отрицательная корректировка превысит баланс

---

## Response: WalletOperationResponse

Ответ после любой операции (deposit/withdraw/payment/refund/correction):

```json
{
  "success": true,
  "wallet_id": 1,
  "new_balance": 1500.0,
  "transaction_id": 42,
  "message": "Deposited 500.00 RUB"
}
```

---

## Ошибки

| Code | Условие |
|------|---------|
| `400` | Недостаточно средств (withdraw/payment/negative correction) |
| `403` | Кошелёк заблокирован (`is_blocked=1`) |
| `404` | User not found / Booking not found |

---

## Примеры использования (bot/app/utils/api.py)

```python
# Получить кошелёк
wallet = await api.get_wallet(user_id=123)
# {"id": 1, "user_id": 123, "balance": 1500.0, "currency": "RUB", "is_blocked": false}

# История транзакций
txs = await api.get_wallet_transactions(user_id=123, limit=20)

# Пополнение
result = await api.wallet_deposit(user_id=123, amount=500, description="Наличные")
# {"success": true, "new_balance": 2000.0, "transaction_id": 42}

# Оплата записи
result = await api.wallet_payment(user_id=123, amount=1000, booking_id=456)

# Возврат
result = await api.wallet_refund(user_id=123, amount=500, booking_id=456)

# Корректировка (admin)
result = await api.wallet_correction(
    user_id=123,
    amount=-100,
    description="Штраф за неявку",
    created_by=1
)
```


