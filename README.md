# Система записи

## Оглавление
* [Введение](#введение)  
* [Архитектура](#архитектура)  
* [Установка](#установка)  
* [Структура базы данных](#структура-базы-данных)  
* [Веб-интерфейсы](#веб-интерфейсы)  
  * [Админ-панель](#админ-панель)  
  * [Пользовательский сайт](#пользовательский-сайт)  
  * [Telegram-бот и Mini App](#telegram-бот-и-mini-app)  
* [Backend и API](#backend-и-api)  
* [Работа с клиентами](#работа-с-клиентами)  
* [Финансы и CRM](#финансы-и-crm)  
* [Примеры использования](#примеры-использования)  
  * [Базовый пример](#базовый-пример)  
  * [Продвинутый пример](#продвинутый-пример)  
* [Дальнейшие планы](#дальнейшие-планы)  
* [Лицензия](#лицензия)  

---

## Введение
**Система записи** — комплексное решение для клиник, студий и сервисных организаций.  
Она объединяет три пользовательских канала:  
- Админ-панель для управления объектами, услугами, специалистами и финансами.  
- Пользовательский сайт для онлайн-бронирования.  
- Telegram-бот (включая Mini App), где клиент может записываться и управлять услугами.  

---

## Архитектура



| Данные                                              | Где хранить | Зачем                      |
| --------------------------------------------------- | ----------- | -------------------------- |
| Справочники (услуги, специалисты, клиенты, локации) | PostgreSQL  | Истина, долговечные данные |
| Финансы (wallet, transactions)                      | PostgreSQL  | Истина, нужна точность     |
| Графики и слоты                                     | PostgreSQL  | Истина                     |
| Быстрая проверка слотов                             | Redis       | Кэш + блокировки           |
| Предварительное бронирование                        | Redis       | TTL + предотвращение гонок |
| Уведомления / события                               | Redis       | Pub/Sub                    |
| Сессии пользователей                                | Redis       | Временное хранилище        |

<details>
  <summary>Нажмите, чтобы увидеть подробности</summary>
  ```mermaid
sequenceDiagram
    participant C as Клиент (браузер/PWA)
    participant API as FastAPI (REST /appointments)
    participant R as Redis (Cache + Pub/Sub)
    participant DB as PostgreSQL
    participant N as Notifier (WebPush/VAPID)
    C->>API: POST /appointments/book {...}
    API->>R: SETNX slot:<loc>:<time> reserved EX 120
    alt слот занят
        API-->>C: Ошибка
    else
        API-->>C: Слот предварительно забронирован
    end
    C->>API: POST /appointments/confirm {...}
    API->>DB: INSERT appointments
    API->>R: DEL slot:<loc>:<time>
    API->>R: PUBLISH appointments "created:{id}"
    API-->>C: ✅ Подтверждено
    R-->>N: событие "appointment created"
    N->>DB: SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE client_id=...
    N-->>C: WebPush уведомление (через VAPID)
  ```
</details>

---

## Установка

<details>
  <summary>Нажмите, чтобы увидеть инструкции</summary>

1. Установить зависимости:  
   - Python 3.11+  
   - Node.js 18+  
   - PostgreSQL 15+  
   - Redis  

2. Склонировать проект:  
   ```bash
   git clone https://github.com/your-org/booking-system.git
   cd booking-system
   ```

3. Настроить `.env`:
   ```env
   DATABASE_URL=postgresql://user:pass@localhost:5432/booking
   REDIS_URL=redis://localhost:6379/0
   SECRET_KEY=...
   ```

4. Запустить миграции БД:  
   ```bash
   alembic upgrade head
   ```

5. Запустить backend и frontend.  

</details>

---

## Структура базы данных

<details>
  <summary>Нажмите, чтобы увидеть ER-диаграмму</summary>
```mermaid
erDiagram
    LOCATIONS {
        int id PK
        text name
        text country
        text region
        text city
        text street
        text house
        text building
        text office
        text postal_code
        int capacity
        bool is_active
        text notes
    }

    LOCATION_SCHEDULES {
        int id PK
        int location_id FK
        int day_of_week
        time start_time
        time end_time
        bool is_day_off
    }

    HOLIDAYS {
        int id PK
        int location_id FK
        date date
        bool is_working
        text description
    }

    WORKPLACES {
        int id PK
        int location_id FK
        text name
        text kind
        int capacity
        text equipment
        bool is_mobile
        int display_order
        text notes
        bool is_active
    }

    SERVICES {
        int id PK
        text name
        text description
        text category
        int duration_min
        int break_min
        numeric price
        text color_code
        int min_age
        int max_age
        bool is_package
        int package_quantity
        bool is_active
    }

    SERVICE_PACKAGES {
        int id PK
        text name
        text description
        int service_id FK
        int quantity
        numeric package_price
        bool is_active
    }

    WORKPLACE_SERVICES {
        int id PK
        int workplace_id FK
        int service_id FK
        bool is_active
        text notes
    }

    SPECIALISTS {
        int id PK
        text first_name
        text last_name
        text name
        text iname
        text specialization
        text phone
        text email
        bigint tg_id
        text notes
        bool is_active
    }

    SERVICE_SPECIALISTS {
        int id PK
        int service_id FK
        int specialist_id FK
        bool is_default
        bool is_active
        text notes
    }

    SPECIALIST_SCHEDULES {
        int id PK
        int specialist_id FK
        int location_id FK
        int workplace_id FK
        int day_of_week
        time start_time
        time end_time
        bool is_day_off
    }

    BREAKS {
        int id PK
        int specialist_id FK
        date date
        time start_time
        time end_time
        text reason
    }

    CLIENTS {
        int id PK
        bigint tg_id
        text phone
        text email
        text first_name
        text last_name
        text middle_name
        text iname
        date birth_date
        text gender
        text notes
        bool is_active
    }

    CLIENT_DISCOUNTS {
        int id PK
        int client_id FK
        numeric discount_percent
        date valid_from
        date valid_to
        text description
    }

    CLIENT_PACKAGES {
        int id PK
        int client_id FK
        int service_id FK
        int total_quantity
        int used_quantity
        timestamp purchased_at
        date valid_to
        text notes
    }

    CLIENT_WALLETS {
        int client_id PK
        numeric balance
    }

    WALLET_TRANSACTIONS {
        int id PK
        int client_id FK
        int appointment_id FK
        numeric amount
        text type
        text description
        text created_by
        timestamp created_at
    }

    APPOINTMENTS {
        int id PK
        int location_id FK
        int service_id FK
        int workplace_id FK
        int specialist_id FK
        int client_id FK
        timestamp start_time
        timestamp end_time
        text status
        numeric final_price
        text notes
        text cancel_reason
        timestamp created_at
        timestamp updated_at
    }

    APPOINTMENT_DISCOUNTS {
        int id PK
        int appointment_id FK
        numeric discount_percent
        text discount_reason
    }

    PUSH_SUBSCRIPTIONS {
        int id PK
        int client_id FK
        text endpoint
        text p256dh
        text auth
        timestamp created_at
    }

    %% Связи
    LOCATIONS ||--o{ LOCATION_SCHEDULES : has
    LOCATIONS ||--o{ HOLIDAYS : has
    LOCATIONS ||--o{ WORKPLACES : has

    WORKPLACES ||--o{ WORKPLACE_SERVICES : provides
    SERVICES   ||--o{ WORKPLACE_SERVICES : available_in

    SERVICES     ||--o{ SERVICE_SPECIALISTS : can_do
    SPECIALISTS  ||--o{ SERVICE_SPECIALISTS : qualified

    SPECIALISTS ||--o{ SPECIALIST_SCHEDULES : works_in
    LOCATIONS   ||--o{ SPECIALIST_SCHEDULES : schedules
    WORKPLACES  ||--o{ SPECIALIST_SCHEDULES : assigned_to

    SPECIALISTS ||--o{ BREAKS : has

    CLIENTS   ||--o{ APPOINTMENTS : books
    LOCATIONS ||--o{ APPOINTMENTS : at
    WORKPLACES||--o{ APPOINTMENTS : in
    SERVICES  ||--o{ APPOINTMENTS : booked
    SPECIALISTS ||--o{ APPOINTMENTS : performs

    CLIENTS ||--|| CLIENT_WALLETS : owns
    CLIENTS ||--o{ WALLET_TRANSACTIONS : has
    APPOINTMENTS ||--o{ WALLET_TRANSACTIONS : related_to

    APPOINTMENTS ||--o{ APPOINTMENT_DISCOUNTS : discounted
    CLIENTS ||--o{ CLIENT_DISCOUNTS : has
    CLIENTS ||--o{ CLIENT_PACKAGES : owns
    SERVICES ||--o{ CLIENT_PACKAGES : package_of
    SERVICES ||--o{ SERVICE_PACKAGES : template_for

    CLIENTS ||--o{ PUSH_SUBSCRIPTIONS : notified
</details>

---

## Веб-интерфейсы

### Админ-панель
- управление филиалами, кабинетами, графиками;  
- добавление и редактирование услуг, пакетов;  
- назначение специалистов и их расписаний;  
- отчётность и аналитика.  

### Пользовательский сайт
- выбор локации, услуги, специалиста;  
- онлайн-бронирование и оплата;  
- покупка пакетов услуг;  
- личный кабинет.  

### Telegram-бот и Mini App
- запись через чат-бота;  
- напоминания и уведомления;  
- возможность открыть мобильный сайт внутри Telegram.  

---

## Backend и API
- **FastAPI**: REST (и опционально GraphQL).  
- PostgreSQL: хранение данных.  
- Redis: слоты, блокировки, pub/sub.  
- Авторизация: JWT или аналог.  

---

## Работа с клиентами
- регистрация и управление клиентами;  
- персональные скидки (`client_discounts`);  
- пакеты услуг (`client_packages`);  
- уведомления (WebPush, Telegram).  

---

## Финансы и CRM
- учёт балансов (`client_wallets`);  
- транзакции (`wallet_transactions`) с типами: deposit, withdraw, payment, refund, correction;  
- связь транзакций с `appointments`;  
- возвраты и корректировки.  

---

## Примеры использования

### Базовый пример
1. Админ создаёт услугу «Массаж 60 мин».  
2. Клиент записывается через сайт или бота.  
3. Оплата списывается с баланса, создаётся запись в `wallet_transactions`.  

### Продвинутый пример
1. Админ создаёт пакет «5 массажей по цене 4».  
2. Клиент покупает пакет, запись в `client_packages`.  
3. При бронировании услуги у клиента списывается 1 посещение из пакета.  

---

## Дальнейшие планы
- интеграция с внешними платёжными сервисами;  
- графический редактор расписаний;  
- модуль аналитики;  
- расширенные уведомления (Email, WhatsApp).  

---

## Лицензия
MIT или иная выбранная вами.  
