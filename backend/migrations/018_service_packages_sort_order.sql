ALTER TABLE service_packages ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;
UPDATE service_packages SET sort_order = id;
