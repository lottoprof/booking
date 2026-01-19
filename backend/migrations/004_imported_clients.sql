-- 004_imported_clients.sql
-- Таблица для импортированных клиентов (CSV/SQL)
-- Опциональная — бот работает и без неё
-- sqlite3 booking.db < schema/migrations/004_imported_clients.sql

CREATE TABLE IF NOT EXISTS imported_clients (
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

CREATE INDEX IF NOT EXISTS idx_imported_clients_phone 
ON imported_clients(phone);

-- Фиксируем версию миграции
INSERT INTO schema_migrations (version) VALUES (4);
