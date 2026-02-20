-- =============================================
-- UPGRADE Booking — Full SQLite Schema
-- Consolidated from migrations 001–016
-- =============================================
--
-- Usage (fresh server):
--   sqlite3 data/sqlite/booking.db < schema/schema_sqlite.sql
--   python scripts/init_admin.py
--

-- ── Company ───────────────────────────────────

CREATE TABLE company (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ── Locations ─────────────────────────────────

CREATE TABLE locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    country TEXT,
    region TEXT,
    city TEXT NOT NULL,
    street TEXT,
    house TEXT,
    building TEXT,
    office TEXT,
    postal_code TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    work_schedule TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    remind_before_minutes INTEGER NOT NULL DEFAULT 120,
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

-- ── Rooms ─────────────────────────────────────

CREATE TABLE rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    display_order INTEGER,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_rooms_location_name ON rooms (location_id, name);

-- ── Roles ─────────────────────────────────────

CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

INSERT OR IGNORE INTO roles (name) VALUES
    ('admin'),
    ('manager'),
    ('specialist'),
    ('client');

-- ── Users ─────────────────────────────────────

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT,
    middle_name TEXT,
    email TEXT,
    phone TEXT,
    tg_id INTEGER,
    tg_username TEXT,
    birth_date TEXT,
    gender TEXT CHECK (gender IN ('male','female','other')),
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

-- ── User Roles ────────────────────────────────

CREATE TABLE user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    location_id INTEGER,
    UNIQUE(user_id, role_id, location_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
);

-- ── Services ──────────────────────────────────

CREATE TABLE services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    duration_min INTEGER NOT NULL,
    break_min INTEGER NOT NULL DEFAULT 0,
    price REAL NOT NULL,
    color_code TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    price_5 REAL,
    price_10 REAL,
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

-- ── Service Packages ──────────────────────────

CREATE TABLE service_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    package_items TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    show_on_pricing INTEGER NOT NULL DEFAULT 1,
    show_on_booking INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

-- ── Service Rooms ─────────────────────────────

CREATE TABLE service_rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    UNIQUE(room_id, service_id),
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
);

-- ── Specialists ───────────────────────────────

CREATE TABLE specialists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    display_name TEXT,
    description TEXT,
    photo_url TEXT,
    work_schedule TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ── Specialist Services ───────────────────────

CREATE TABLE specialist_services (
    service_id INTEGER NOT NULL,
    specialist_id INTEGER NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    UNIQUE(service_id, specialist_id),
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (specialist_id) REFERENCES specialists(id) ON DELETE CASCADE
);

-- ── Calendar Overrides ────────────────────────

CREATE TABLE calendar_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL CHECK (
        target_type IN ('location','room','specialist','service','system')
    ),
    target_id INTEGER,
    date_start TEXT NOT NULL,
    date_end   TEXT NOT NULL,
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
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- ── Bookings ──────────────────────────────────

CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    room_id INTEGER,
    client_id INTEGER NOT NULL,
    specialist_id INTEGER NOT NULL,
    date_start TEXT NOT NULL,
    date_end   TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    break_minutes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending','confirmed','cancelled','done','no_show')
    ),
    final_price REAL,
    notes TEXT,
    cancel_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    client_package_id INTEGER REFERENCES client_packages(id) ON DELETE SET NULL,
    service_package_id INTEGER REFERENCES service_packages(id),

    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (service_id) REFERENCES services(id),
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (client_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (specialist_id) REFERENCES specialists(id) ON DELETE CASCADE
);

-- ── Client Packages ───────────────────────────

CREATE TABLE client_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    package_id INTEGER NOT NULL,
    used_quantity INTEGER NOT NULL DEFAULT 0,
    purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_to TEXT,
    notes TEXT,
    used_items TEXT NOT NULL DEFAULT '{}',
    is_closed INTEGER NOT NULL DEFAULT 0,
    purchase_price REAL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (package_id) REFERENCES service_packages(id) ON DELETE CASCADE
);

-- ── Client Discounts ──────────────────────────

CREATE TABLE client_discounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    discount_percent REAL NOT NULL DEFAULT 0,
    valid_from TEXT,
    valid_to TEXT,
    description TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ── Booking Discounts ─────────────────────────

CREATE TABLE booking_discounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    discount_percent REAL NOT NULL DEFAULT 0,
    discount_reason TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

-- ── Client Wallets ────────────────────────────

CREATE TABLE client_wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    balance REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'RUB',
    is_blocked INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ── Wallet Transactions ───────────────────────

CREATE TABLE wallet_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    booking_id INTEGER,
    amount REAL NOT NULL,
    type TEXT NOT NULL DEFAULT 'payment'
        CHECK (type IN ('deposit','withdraw','payment','refund','correction')),
    description TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (wallet_id) REFERENCES client_wallets(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- ── Push Subscriptions ────────────────────────

CREATE TABLE push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    endpoint TEXT NOT NULL,
    auth TEXT,
    p256dh TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ── Audit Log ─────────────────────────────────

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor_user_id INTEGER,
    target_user_id INTEGER,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_created_at ON audit_log(created_at);

-- ── Imported Clients ──────────────────────────

CREATE TABLE imported_clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    notes TEXT,
    matched_user_id INTEGER,
    matched_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (matched_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_imported_clients_phone ON imported_clients(phone);

-- ── Notification Settings ─────────────────────

CREATE TABLE notification_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    recipient_role TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'all',
    enabled INTEGER NOT NULL DEFAULT 1,
    ad_template_id INTEGER,
    company_id INTEGER NOT NULL,
    UNIQUE(event_type, recipient_role, channel, company_id),
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

-- Seed: notification_settings (company_id=1, создаётся init_admin.py)
INSERT OR IGNORE INTO notification_settings (event_type, recipient_role, channel, enabled, company_id) VALUES
    ('booking_created',     'admin',      'all', 1, 1),
    ('booking_created',     'specialist', 'all', 1, 1),
    ('booking_created',     'client',     'all', 1, 1),
    ('booking_cancelled',   'admin',      'all', 1, 1),
    ('booking_cancelled',   'specialist', 'all', 1, 1),
    ('booking_cancelled',   'client',     'all', 1, 1),
    ('booking_rescheduled', 'admin',      'all', 1, 1),
    ('booking_rescheduled', 'specialist', 'all', 1, 1),
    ('booking_rescheduled', 'client',     'all', 1, 1),
    ('booking_done',        'admin',      'all', 1, 1),
    ('booking_done',        'manager',    'all', 1, 1),
    ('booking_reminder',    'client',     'all', 1, 1);

-- ── Ad Templates ──────────────────────────────

CREATE TABLE ad_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content_tg TEXT NOT NULL,
    content_html TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    valid_until TEXT,
    company_id INTEGER NOT NULL,
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

-- ── Specialist Integrations (Google Calendar) ─

CREATE TABLE specialist_integrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    specialist_id INTEGER REFERENCES specialists(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'google_calendar',
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TEXT,
    calendar_id TEXT DEFAULT 'primary',
    sync_enabled INTEGER DEFAULT 1,
    sync_scope TEXT DEFAULT 'own',
    location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    last_sync_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(specialist_id, provider)
);

CREATE INDEX idx_specialist_integrations_specialist_id ON specialist_integrations(specialist_id);
CREATE INDEX idx_specialist_integrations_user_id ON specialist_integrations(user_id);

-- ── Booking External Events ───────────────────

CREATE TABLE booking_external_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    provider TEXT NOT NULL DEFAULT 'google_calendar',
    external_event_id TEXT NOT NULL,
    specialist_integration_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (specialist_integration_id) REFERENCES specialist_integrations(id) ON DELETE CASCADE,
    UNIQUE(booking_id, specialist_integration_id)
);

CREATE INDEX idx_booking_external_events_booking_id ON booking_external_events(booking_id);
CREATE INDEX idx_booking_external_events_external_event_id ON booking_external_events(external_event_id);

-- ── Categories (Blog) ─────────────────────────

CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO categories (slug, name, sort_order) VALUES
    ('services',  'Услуги',             1),
    ('body-care', 'Уход за телом',      2),
    ('results',   'Результаты',         3),
    ('faq',       'Ответы на вопросы',  4);

-- ── Articles (Blog) ───────────────────────────

CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    meta_description TEXT,
    category_id INTEGER REFERENCES categories(id),
    body_html TEXT NOT NULL,
    image_url TEXT,
    is_published INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    published_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ── Promotions ────────────────────────────────

CREATE TABLE promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    badge_type TEXT NOT NULL DEFAULT 'sale',
    badge_text TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    price_new INTEGER,
    price_old INTEGER,
    end_date TEXT,
    cta_text TEXT,
    cta_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ── Schema Migrations ─────────────────────────

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Mark all existing migrations as applied
INSERT OR IGNORE INTO schema_migrations (version) VALUES
    (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12),(13),(14),(15),(16);
