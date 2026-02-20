-- =============================================
-- UPGRADE Booking — Full PostgreSQL Schema
-- Consolidated from migrations 001–016
-- =============================================
--
-- Reference schema. Primary deployment uses SQLite.
--

-- ── Company ───────────────────────────────────

CREATE TABLE company (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE company IS 'Компания-владелец локаций и пользователей.';

-- ── Locations ─────────────────────────────────

CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    country TEXT,
    region TEXT,
    city TEXT NOT NULL,
    street TEXT,
    house TEXT,
    building TEXT,
    office TEXT,
    postal_code TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    work_schedule JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    remind_before_minutes INT NOT NULL DEFAULT 120
);

COMMENT ON TABLE locations IS 'Справочник локаций (адреса, филиалы, студии).';
COMMENT ON COLUMN locations.work_schedule IS 'График работы локации в формате JSON: интервалы по дням недели.';
COMMENT ON COLUMN locations.remind_before_minutes IS 'За сколько минут до визита отправлять напоминание клиенту.';

-- ── Rooms ─────────────────────────────────────

CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    location_id INT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    display_order INT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX uq_rooms_location_name ON rooms (location_id, name);

COMMENT ON TABLE rooms IS 'Кабинеты / комнаты внутри локации.';

-- ── Roles ─────────────────────────────────────

CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

INSERT INTO roles (name) VALUES
    ('admin'),
    ('manager'),
    ('specialist'),
    ('client');

COMMENT ON TABLE roles IS 'Справочник ролей пользователей.';

-- ── Users ─────────────────────────────────────

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    middle_name TEXT,
    email TEXT,
    phone TEXT,
    tg_id BIGINT,
    tg_username TEXT,
    birth_date DATE,
    gender TEXT CHECK (gender IN ('male','female','other')),
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE users IS 'Пользователи системы (админ, специалист, клиент).';

-- ── User Roles ────────────────────────────────

CREATE TABLE user_roles (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    UNIQUE(user_id, role_id, location_id)
);

COMMENT ON TABLE user_roles IS 'Назначение ролей пользователю. Для специалистов и менеджеров может содержать привязку к локации.';

-- ── Services ──────────────────────────────────

CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    duration_min INT NOT NULL,
    break_min INT NOT NULL DEFAULT 0,
    price NUMERIC(10,2) NOT NULL,
    color_code TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    price_5 NUMERIC(10,2),
    price_10 NUMERIC(10,2)
);

COMMENT ON TABLE services IS 'Справочник услуг для записи.';
COMMENT ON COLUMN services.price_5 IS 'Цена за сеанс при покупке курса из 5.';
COMMENT ON COLUMN services.price_10 IS 'Цена за сеанс при покупке курса из 10.';

-- ── Service Packages ──────────────────────────

CREATE TABLE service_packages (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    package_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    show_on_pricing BOOLEAN NOT NULL DEFAULT TRUE,
    show_on_booking BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE service_packages IS 'Пакеты услуг (комплексы из одной или нескольких услуг).';
COMMENT ON COLUMN service_packages.package_items IS 'JSON-массив: service_id + quantity.';
COMMENT ON COLUMN service_packages.show_on_pricing IS 'Показывать на странице /pricing.';
COMMENT ON COLUMN service_packages.show_on_booking IS 'Показывать при бронировании.';

-- ── Service Rooms ─────────────────────────────

CREATE TABLE service_rooms (
    id SERIAL PRIMARY KEY,
    room_id INT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    UNIQUE(room_id, service_id)
);

COMMENT ON TABLE service_rooms IS 'Привязка услуг к комнатам (кабинетам).';

-- ── Specialists ───────────────────────────────

CREATE TABLE specialists (
    id SERIAL PRIMARY KEY,
    user_id INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT,
    description TEXT,
    photo_url TEXT,
    work_schedule JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE specialists IS 'Профили специалистов. Расширение данных users.';

-- ── Specialist Services ───────────────────────

CREATE TABLE specialist_services (
    service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    UNIQUE(service_id, specialist_id)
);

COMMENT ON TABLE specialist_services IS 'Компетенции специалистов: какие услуги они оказывают.';

-- ── Calendar Overrides ────────────────────────

CREATE TABLE calendar_overrides (
    id SERIAL PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (
        target_type IN ('location','room','specialist','service','system')
    ),
    target_id INT,
    date_start TIMESTAMP NOT NULL,
    date_end   TIMESTAMP NOT NULL,
    override_kind TEXT NOT NULL CHECK (
        override_kind IN (
            'day_off',
            'block',
            'cleaning',
            'maintenance',
            'admin_hold'
        )
    ),
    reason TEXT,
    created_by INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE calendar_overrides IS 'Универсальная таблица блокировок времени.';

-- ── Bookings ──────────────────────────────────

CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    location_id INT NOT NULL REFERENCES locations(id),
    service_id INT NOT NULL REFERENCES services(id),
    room_id INT REFERENCES rooms(id),
    client_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    specialist_id INT NOT NULL REFERENCES specialists(id) ON DELETE CASCADE,
    date_start TIMESTAMP NOT NULL,
    date_end   TIMESTAMP NOT NULL,
    duration_minutes INT NOT NULL,
    break_minutes INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending','confirmed','cancelled','done','no_show')
    ),
    final_price NUMERIC(10,2),
    notes TEXT,
    cancel_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    client_package_id INT REFERENCES client_packages(id) ON DELETE SET NULL,
    service_package_id INT REFERENCES service_packages(id)
);

COMMENT ON TABLE bookings IS 'Записи клиентов на услуги.';

-- ── Client Packages ───────────────────────────

CREATE TABLE client_packages (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package_id INT NOT NULL REFERENCES service_packages(id) ON DELETE CASCADE,
    used_quantity INT NOT NULL DEFAULT 0,
    purchased_at TIMESTAMP NOT NULL DEFAULT now(),
    valid_to DATE,
    notes TEXT,
    used_items JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_closed BOOLEAN NOT NULL DEFAULT FALSE,
    purchase_price NUMERIC(10,2)
);

COMMENT ON TABLE client_packages IS 'Купленные клиентами пакеты услуг.';
COMMENT ON COLUMN client_packages.used_items IS 'JSON: {"service_id": quantity} — учёт использования по услугам.';
COMMENT ON COLUMN client_packages.is_closed IS 'Пакет закрыт (использован полностью или вручную).';
COMMENT ON COLUMN client_packages.purchase_price IS 'Цена на момент покупки (snapshot).';

-- ── Client Discounts ──────────────────────────

CREATE TABLE client_discounts (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    valid_from DATE,
    valid_to DATE,
    description TEXT
);

COMMENT ON TABLE client_discounts IS 'Персональные скидки клиентов. user_id=NULL — промо для всех.';

-- ── Booking Discounts ─────────────────────────

CREATE TABLE booking_discounts (
    id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    discount_reason TEXT
);

COMMENT ON TABLE booking_discounts IS 'Разовые скидки, применённые к конкретной записи.';

-- ── Client Wallets ────────────────────────────

CREATE TABLE client_wallets (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'RUB',
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE client_wallets IS 'Кошельки клиентов. Текущий баланс.';

-- ── Wallet Transactions ───────────────────────

CREATE TABLE wallet_transactions (
    id SERIAL PRIMARY KEY,
    wallet_id INT NOT NULL REFERENCES client_wallets(id) ON DELETE CASCADE,
    booking_id INT REFERENCES bookings(id) ON DELETE SET NULL,
    amount NUMERIC(12,2) NOT NULL,
    type TEXT NOT NULL DEFAULT 'payment'
        CHECK (type IN ('deposit','withdraw','payment','refund','correction')),
    description TEXT,
    created_by INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE wallet_transactions IS 'Финансовые операции по клиентским кошелькам.';

-- ── Push Subscriptions ────────────────────────

CREATE TABLE push_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    auth TEXT,
    p256dh TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE push_subscriptions IS 'Подписки клиентов на WebPush (VAPID).';

-- ── Audit Log ─────────────────────────────────

CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    target_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    payload TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_created_at ON audit_log(created_at);

COMMENT ON TABLE audit_log IS 'Лог аудита действий пользователей.';

-- ── Imported Clients ──────────────────────────

CREATE TABLE imported_clients (
    id SERIAL PRIMARY KEY,
    phone TEXT NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    notes TEXT,
    matched_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    matched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_imported_clients_phone ON imported_clients(phone);

COMMENT ON TABLE imported_clients IS 'Импортированные клиенты (сопоставление по телефону).';

-- ── Notification Settings ─────────────────────

CREATE TABLE notification_settings (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    recipient_role TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'all',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ad_template_id INT,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE,
    UNIQUE(event_type, recipient_role, channel, company_id)
);

INSERT INTO notification_settings (event_type, recipient_role, channel, enabled, company_id) VALUES
    ('booking_created',     'admin',      'all', TRUE, 1),
    ('booking_created',     'specialist', 'all', TRUE, 1),
    ('booking_created',     'client',     'all', TRUE, 1),
    ('booking_cancelled',   'admin',      'all', TRUE, 1),
    ('booking_cancelled',   'specialist', 'all', TRUE, 1),
    ('booking_cancelled',   'client',     'all', TRUE, 1),
    ('booking_rescheduled', 'admin',      'all', TRUE, 1),
    ('booking_rescheduled', 'specialist', 'all', TRUE, 1),
    ('booking_rescheduled', 'client',     'all', TRUE, 1),
    ('booking_done',        'admin',      'all', TRUE, 1),
    ('booking_done',        'manager',    'all', TRUE, 1),
    ('booking_reminder',    'client',     'all', TRUE, 1);

COMMENT ON TABLE notification_settings IS 'Маршрутизация уведомлений по событиям и ролям.';

-- ── Ad Templates ──────────────────────────────

CREATE TABLE ad_templates (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    content_tg TEXT NOT NULL,
    content_html TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    valid_until TIMESTAMP,
    company_id INT NOT NULL REFERENCES company(id) ON DELETE CASCADE
);

COMMENT ON TABLE ad_templates IS 'Рекламные шаблоны, встраиваемые в уведомления.';

-- ── Specialist Integrations (Google Calendar) ─

CREATE TABLE specialist_integrations (
    id SERIAL PRIMARY KEY,
    specialist_id INT REFERENCES specialists(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'google_calendar',
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    calendar_id TEXT DEFAULT 'primary',
    sync_enabled BOOLEAN DEFAULT TRUE,
    sync_scope TEXT DEFAULT 'own',
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE(specialist_id, provider)
);

CREATE INDEX idx_specialist_integrations_specialist_id ON specialist_integrations(specialist_id);
CREATE INDEX idx_specialist_integrations_user_id ON specialist_integrations(user_id);

COMMENT ON TABLE specialist_integrations IS 'OAuth-интеграции специалистов с внешними календарями.';
COMMENT ON COLUMN specialist_integrations.sync_scope IS 'own — свои букинги, location — вся локация, all — все.';

-- ── Booking External Events ───────────────────

CREATE TABLE booking_external_events (
    id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'google_calendar',
    external_event_id TEXT NOT NULL,
    specialist_integration_id INT NOT NULL REFERENCES specialist_integrations(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE(booking_id, specialist_integration_id)
);

CREATE INDEX idx_booking_external_events_booking_id ON booking_external_events(booking_id);
CREATE INDEX idx_booking_external_events_external_event_id ON booking_external_events(external_event_id);

COMMENT ON TABLE booking_external_events IS 'Связь букингов с событиями во внешних календарях.';

-- ── Categories (Blog) ─────────────────────────

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT now()
);

INSERT INTO categories (slug, name, sort_order) VALUES
    ('services',  'Услуги',             1),
    ('body-care', 'Уход за телом',      2),
    ('results',   'Результаты',         3),
    ('faq',       'Ответы на вопросы',  4);

COMMENT ON TABLE categories IS 'Категории статей блога.';

-- ── Articles (Blog) ───────────────────────────

CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    meta_description TEXT,
    category_id INT REFERENCES categories(id),
    body_html TEXT NOT NULL,
    image_url TEXT,
    is_published BOOLEAN DEFAULT FALSE,
    sort_order INT DEFAULT 0,
    published_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT now(),
    created_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE articles IS 'Статьи блога.';

-- ── Promotions ────────────────────────────────

CREATE TABLE promotions (
    id SERIAL PRIMARY KEY,
    badge_type TEXT NOT NULL DEFAULT 'sale',
    badge_text TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    price_new INT,
    price_old INT,
    end_date DATE,
    cta_text TEXT,
    cta_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

COMMENT ON TABLE promotions IS 'Промо-блоки на главной странице.';

-- ── Schema Migrations ─────────────────────────

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_migrations (version) VALUES
    (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12),(13),(14),(15),(16);
