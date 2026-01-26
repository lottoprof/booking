-- 005_notification_tables.sql
-- Notification settings and ad templates for the universal notification system.

CREATE TABLE IF NOT EXISTS notification_settings (
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

CREATE TABLE IF NOT EXISTS ad_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content_tg TEXT NOT NULL,
    content_html TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    valid_until TEXT,
    company_id INTEGER NOT NULL,
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

-- Seed default notification settings for company_id=1
-- booking_created
INSERT OR IGNORE INTO notification_settings (event_type, recipient_role, channel, enabled, company_id)
VALUES
    ('booking_created', 'admin', 'all', 1, 1),
    ('booking_created', 'specialist', 'all', 1, 1),
    ('booking_created', 'client', 'all', 1, 1),
    ('booking_cancelled', 'admin', 'all', 1, 1),
    ('booking_cancelled', 'specialist', 'all', 1, 1),
    ('booking_cancelled', 'client', 'all', 1, 1),
    ('booking_rescheduled', 'admin', 'all', 1, 1),
    ('booking_rescheduled', 'specialist', 'all', 1, 1),
    ('booking_rescheduled', 'client', 'all', 1, 1);
