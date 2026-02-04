-- Migration 013: Make specialist_id nullable for admin/manager integrations
-- SQLite doesn't support ALTER COLUMN, need to recreate table

CREATE TABLE specialist_integrations_new (
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

INSERT INTO specialist_integrations_new
SELECT * FROM specialist_integrations;

DROP TABLE specialist_integrations;

ALTER TABLE specialist_integrations_new RENAME TO specialist_integrations;

CREATE INDEX idx_specialist_integrations_user_id ON specialist_integrations(user_id);
