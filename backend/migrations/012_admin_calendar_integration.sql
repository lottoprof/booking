-- Migration 012: Admin/Manager Google Calendar integration
-- Allows admins and managers to sync all bookings to their calendar

-- Add user_id column to specialist_integrations for admin/manager use
-- When specialist_id is NULL and user_id is set - it's an admin/manager integration
ALTER TABLE specialist_integrations ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

-- Add scope column to define what bookings to sync
-- 'own' = only own bookings (specialist default)
-- 'location' = all bookings for specific location (manager)
-- 'all' = all bookings across all locations (admin)
ALTER TABLE specialist_integrations ADD COLUMN sync_scope TEXT DEFAULT 'own';

-- Add location_id for manager-level sync (optional, NULL = all locations)
ALTER TABLE specialist_integrations ADD COLUMN location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE;

-- Create index for user_id lookups
CREATE INDEX idx_specialist_integrations_user_id ON specialist_integrations(user_id);
