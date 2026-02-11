-- 015_contract_schema.sql
-- Align DB schema with docs/contract.md

-- 1. services: price tiers for packages
ALTER TABLE services ADD COLUMN price_5 REAL;
ALTER TABLE services ADD COLUMN price_10 REAL;

-- 2. service_packages: drop package_price, add visibility flags
--    SQLite <3.35 does not support DROP COLUMN; recreate table.
CREATE TABLE service_packages_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    package_items TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    show_on_pricing INTEGER NOT NULL DEFAULT 1,
    show_on_booking INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE
);

INSERT INTO service_packages_new (id, company_id, name, description, package_items, is_active, show_on_pricing, show_on_booking)
SELECT id, company_id, name, description, package_items, is_active, 1, 1
FROM service_packages;

DROP TABLE service_packages;
ALTER TABLE service_packages_new RENAME TO service_packages;

-- 3. client_packages: purchase_price (snapshot at time of sale)
ALTER TABLE client_packages ADD COLUMN purchase_price REAL;

-- 4. client_discounts: user_id nullable (NULL = promo for everyone)
CREATE TABLE client_discounts_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    discount_percent REAL NOT NULL DEFAULT 0,
    valid_from TEXT,
    valid_to TEXT,
    description TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT INTO client_discounts_new (id, user_id, discount_percent, valid_from, valid_to, description)
SELECT id, user_id, discount_percent, valid_from, valid_to, description
FROM client_discounts;

DROP TABLE client_discounts;
ALTER TABLE client_discounts_new RENAME TO client_discounts;

-- 5. bookings: link to preset (service_package_id)
ALTER TABLE bookings ADD COLUMN service_package_id INTEGER REFERENCES service_packages(id);
