-- 008_booking_done_manager.sql
-- Add notification settings for booking_done event for manager role.

INSERT OR IGNORE INTO notification_settings (event_type, recipient_role, channel, enabled, company_id)
VALUES
    ('booking_done', 'manager', 'all', 1, 1);
