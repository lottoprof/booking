-- 006_booking_done_settings.sql
-- Add notification settings for booking_done event (completion confirmation).

INSERT OR IGNORE INTO notification_settings (event_type, recipient_role, channel, enabled, company_id)
VALUES
    ('booking_done', 'admin', 'all', 1, 1);
