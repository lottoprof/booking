```
Telegram webhook
    │
    ▼
┌─────────────────┐
│   Gateway:8080  │
│   /tg/webhook   │──► process_update(bot)
└────────┬────────┘           │
         │                    │
         │    ◄───────────────┘
         │    Bot делает HTTP запрос
         ▼    к тому же Gateway
┌─────────────────┐
│   Gateway:8080  │
│   /locations    │  ← X-Internal-Token
│   policy: allow │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Backend:8000   │
└─────────────────┘
```

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

Историческая сущность.

### GET /bookings  
### GET /bookings/{id}  
### POST /bookings  

❌ PATCH — запрещён → **405 Method Not Allowed**  
❌ DELETE — запрещён → **405 Method Not Allowed**

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

