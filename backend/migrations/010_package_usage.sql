-- Migration 010: Package usage tracking
-- Add per-service usage tracking for packages and link bookings to packages

-- 1. Add used_items column (JSON) to track per-service usage
-- Format: {"service_id": quantity_used, ...}
-- Example: {"1": 2, "2": 0} means service 1 used 2 times, service 2 unused
ALTER TABLE client_packages ADD COLUMN used_items TEXT NOT NULL DEFAULT '{}';

-- 2. Add is_closed flag for marking packages as terminated (e.g., after refund)
ALTER TABLE client_packages ADD COLUMN is_closed INTEGER NOT NULL DEFAULT 0;

-- 3. Add client_package_id to bookings for tracking which package was used
ALTER TABLE bookings ADD COLUMN client_package_id INTEGER
    REFERENCES client_packages(id) ON DELETE SET NULL;
