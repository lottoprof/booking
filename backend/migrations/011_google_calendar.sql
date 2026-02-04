-- Migration 011: Google Calendar integration for specialists
-- Allows specialists to connect their Google Calendar for automatic booking sync

-- 1. Table for storing specialist integration credentials
CREATE TABLE specialist_integrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    specialist_id INTEGER NOT NULL,
    provider TEXT NOT NULL DEFAULT 'google_calendar',
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TEXT,
    calendar_id TEXT DEFAULT 'primary',
    sync_enabled INTEGER DEFAULT 1,
    last_sync_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (specialist_id) REFERENCES specialists(id) ON DELETE CASCADE,
    UNIQUE(specialist_id, provider)
);

-- 2. Table for linking bookings to external calendar events
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

-- 3. Index for faster lookups
CREATE INDEX idx_specialist_integrations_specialist_id ON specialist_integrations(specialist_id);
CREATE INDEX idx_booking_external_events_booking_id ON booking_external_events(booking_id);
CREATE INDEX idx_booking_external_events_external_event_id ON booking_external_events(external_event_id);
