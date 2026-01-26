-- 007_booking_status_no_show.sql
-- Add 'no_show' to bookings.status CHECK constraint.
-- SQLite requires table recreation to alter CHECK constraints.

PRAGMA foreign_keys=OFF;

BEGIN TRANSACTION;

CREATE TABLE bookings_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    room_id INTEGER,
    client_id INTEGER NOT NULL,
    specialist_id INTEGER NOT NULL,
    date_start TEXT NOT NULL,
    date_end   TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    break_minutes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending','confirmed','cancelled','done','no_show')
    ),
    final_price REAL,
    notes TEXT,
    cancel_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (service_id) REFERENCES services(id),
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (client_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (specialist_id) REFERENCES specialists(id) ON DELETE CASCADE
);

INSERT INTO bookings_new SELECT * FROM bookings;

DROP TABLE bookings;

ALTER TABLE bookings_new RENAME TO bookings;

COMMIT;

PRAGMA foreign_keys=ON;
