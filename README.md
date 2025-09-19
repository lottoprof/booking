
| Данные                                              | Где хранить | Зачем                      |
| --------------------------------------------------- | ----------- | -------------------------- |
| Справочники (услуги, специалисты, клиенты, локации) | PostgreSQL  | Истина, долговечные данные |
| Финансы (wallet, transactions)                      | PostgreSQL  | Истина, нужна точность     |
| Графики и слоты                                     | PostgreSQL  | Истина                     |
| Быстрая проверка слотов                             | Redis       | Кэш + блокировки           |
| Предварительное бронирование                        | Redis       | TTL + предотвращение гонок |
| Уведомления / события                               | Redis       | Pub/Sub                    |
| Сессии пользователей                                | Redis       | Временное хранилище        |

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


```mermaid
erDiagram

    LOCATIONS {
        int id PK
        text name
        text address
        int capacity
        bool is_active
    }

    LOCATION_SCHEDULES {
        int id PK
        int location_id FK
        int day_of_week
        time start_time
        time end_time
        bool is_day_off
    }

    WORKPLACES {
        int id PK
        int location_id FK
        text name
        text type
        bool is_active
    }

    SERVICES {
        int id PK
        text name
        text description
        int duration_min
        int break_min
        numeric price
        bool is_active
    }

    WORKPLACE_SERVICES {
        int id PK
        int workplace_id FK
        int service_id FK
        numeric price
        int duration_min
        int break_min
        bool is_active
    }

    SPECIALISTS {
        int id PK
        text name
        text specialization
        bool is_active
    }

    SERVICE_SPECIALISTS {
        int id PK
        int service_id FK
        int specialist_id FK
        numeric custom_price
        int custom_duration
        bool is_active
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

    HOLIDAYS {
        int id PK
        int location_id FK
        date date
        bool is_working
        text description
    }

    CLIENTS {
        int id PK
        bigint tg_id
        text phone
        text first_name
        text last_name
        text email
        text notes
        bool is_active
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
        numeric discount
        text description
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
        timestamp created_at
        timestamp updated_at
    }

    %% Связи
    LOCATIONS ||--o{ LOCATION_SCHEDULES : has
    LOCATIONS ||--o{ WORKPLACES : has
    LOCATIONS ||--o{ HOLIDAYS : has
    WORKPLACES ||--o{ WORKPLACE_SERVICES : provides
    SERVICES ||--o{ WORKPLACE_SERVICES : available_in
    SERVICES ||--o{ SERVICE_SPECIALISTS : can_do
    SPECIALISTS ||--o{ SERVICE_SPECIALISTS : qualified
    SPECIALISTS ||--o{ SPECIALIST_SCHEDULES : works_in
    LOCATIONS ||--o{ SPECIALIST_SCHEDULES : schedules
    WORKPLACES ||--o{ SPECIALIST_SCHEDULES : optional
    SPECIALISTS ||--o{ BREAKS : has
    CLIENTS ||--o{ APPOINTMENTS : books
    LOCATIONS ||--o{ APPOINTMENTS : at
    WORKPLACES ||--o{ APPOINTMENTS : in
    SERVICES ||--o{ APPOINTMENTS : booked
    SPECIALISTS ||--o{ APPOINTMENTS : assigned
    CLIENTS ||--|| CLIENT_WALLETS : owns
    CLIENTS ||--o{ WALLET_TRANSACTIONS : makes
    APPOINTMENTS ||--o{ WALLET_TRANSACTIONS : paid_by
```

