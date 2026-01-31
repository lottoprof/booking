# Кошелёк клиента

У клиента один кошелёк → он видит все свои операции.
Транзакции создаются ТОЛЬКО через бизнес-операции (не CRUD).

---

## Таблицы

| Таблица | Назначение |
|---------|------------|
| `client_wallets` | Кошелёк (balance, currency, is_blocked) |
| `wallet_transactions` | История операций (read-only для клиента) |
| `client_packages` | Купленные пакеты услуг |
| `service_packages` | Шаблоны пакетов (что продаём) |

---

## Типы транзакций

| Тип | Сумма | Описание |
|-----|-------|----------|
| `deposit` | + | Пополнение (покупка пакета, начисление за услугу) |
| `withdraw` | − | Списание (использование пакета, оплата услуги, возврат пакета) |
| `payment` | − | Оплата конкретной записи |
| `refund` | + | Возврат средств |
| `correction` | ± | Ручная корректировка (только админ) |

---

## API кошелька

### Базовые операции

```
GET  /wallets/{user_id}              → WalletRead
GET  /wallets/{user_id}/transactions → list[WalletTransactionRead]
POST /wallets/{user_id}/deposit      → WalletOperationResponse
POST /wallets/{user_id}/withdraw     → WalletOperationResponse
POST /wallets/{user_id}/payment      → WalletOperationResponse
POST /wallets/{user_id}/refund       → WalletOperationResponse
POST /wallets/{user_id}/correction   → WalletOperationResponse
```

### Операции с пакетами

```
POST /wallets/{user_id}/package-purchase → WalletPackagePurchaseResponse
POST /wallets/{user_id}/package-refund   → WalletPackageRefundResponse
```

### Просмотр пакетов клиента

```
GET /client_packages/user/{user_id}  → list[ClientPackageWithRemaining]
GET /client_packages/{id}/remaining  → детальный остаток по услугам
```

---

## Пакеты услуг

### Структура пакета

**service_packages** (шаблон):
```json
{
  "id": 2,
  "name": "LPG 10 сеансов",
  "package_items": [{"service_id": 1, "quantity": 10}],
  "package_price": 10000.0
}
```

**client_packages** (покупка клиента):
```json
{
  "id": 1,
  "user_id": 4,
  "package_id": 2,
  "used_items": {"1": 3},
  "is_closed": false,
  "valid_to": "2026-06-01"
}
```

### Цена за единицу

```
unit_price = package_price / sum(quantities)
```

Пример: пакет 10×LPG за 10000₽ → 1000₽/сеанс

---

## Бизнес-процессы

### 1. Продажа пакета

**Триггер:** Админ продаёт пакет клиенту

```
POST /wallets/{user_id}/package-purchase
{
  "package_id": 2,
  "valid_to": "2026-06-01",
  "created_by": 1
}
```

**Результат:**
- Создаётся `client_packages` (used_items = {})
- Создаётся `deposit` транзакция на `package_price`
- Баланс увеличивается

### 2. Подтверждение записи (status=done)

**Триггер:** Админ подтверждает оказание услуги

```
PATCH /bookings/{id}
{"status": "done"}
```

**Алгоритм:**

```
1. Найти активный пакет клиента с этой услугой
   - is_closed = 0
   - valid_to IS NULL OR valid_to >= today
   - remaining > 0
   - ORDER BY valid_to ASC (сначала истекающие)

2. ЕСЛИ пакет найден:
   - used_items[service_id]++
   - withdraw на unit_price
   - booking.client_package_id = пакет

3. ЕСЛИ пакет НЕ найден (одиночная услуга):
   - deposit + withdraw на service.price
   - booking.client_package_id = NULL
```

### 3. Возврат остатка пакета

**Триггер:** Клиент хочет вернуть неиспользованные услуги

```
POST /wallets/{user_id}/package-refund
{
  "client_package_id": 1,
  "reason": "Клиент переезжает",
  "created_by": 1
}
```

**Результат:**
- Рассчитывается `remaining × unit_price`
- Создаётся `withdraw` транзакция
- Пакет закрывается (`is_closed = 1`)

---

## Примеры транзакций

### Сценарий: пакет 10×LPG за 10000₽

| # | amount | type | description |
|---|--------|------|-------------|
| 1 | +10000 | deposit | Покупка пакета: LPG |
| 2 | −1000 | withdraw | Пакет «LPG»: LPG |
| 3 | −1000 | withdraw | Пакет «LPG»: LPG |
| 4 | −8000 | withdraw | Возврат: LPG (8 услуг) |

Итого: 0₽

### Сценарий: одиночная услуга 1500₽

| # | amount | type | description |
|---|--------|------|-------------|
| 1 | +1500 | deposit | Прессотерапия |
| 2 | −1500 | withdraw | Прессотерапия |

Итого: 0₽ (баланс не меняется, но есть аудит)

---

## Связи

```
client_wallets
    ↓ 1:N
wallet_transactions ← booking_id → bookings
                                      ↓
                              client_package_id
                                      ↓
                              client_packages ← package_id → service_packages
```

---

## Принципы

1. **Централизация** — вся финансовая логика в backend
2. **Аудит** — каждая операция создаёт транзакцию
3. **Безопасность** — клиент только смотрит, не редактирует
4. **Приоритет пакетов** — сначала используются истекающие пакеты
5. **Атомарность** — покупка/списание/возврат в одной транзакции БД
