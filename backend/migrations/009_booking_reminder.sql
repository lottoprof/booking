-- 009_booking_reminder.sql
-- Add remind_before_minutes to locations and notification settings for booking_reminder.

BEGIN TRANSACTION;

ALTER TABLE locations ADD COLUMN remind_before_minutes INTEGER NOT NULL DEFAULT 120;

INSERT OR IGNORE INTO notification_settings (event_type, recipient_role, channel, enabled, company_id)
VALUES
    ('booking_reminder', 'client', 'all', 1, 1);

COMMIT;
