PRAGMA foreign_keys=OFF;

CREATE TABLE bookings_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    room_id INTEGER,
    client_id INTEGER NOT NULL,
    specialist_id INTEGER NOT NULL,
    date_start TEXT NOT NULL,
    date_end TEXT NOT NULL,
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
    client_package_id INTEGER REFERENCES client_packages(id) ON DELETE SET NULL,
    service_package_id INTEGER REFERENCES service_packages(id),
    FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (client_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (specialist_id) REFERENCES specialists(id) ON DELETE CASCADE
);

INSERT INTO bookings_new (
    id, company_id, location_id, room_id, client_id, specialist_id,
    date_start, date_end, duration_minutes, break_minutes,
    status, final_price, notes, cancel_reason,
    created_at, updated_at, client_package_id, service_package_id
)
SELECT
    id, company_id, location_id, room_id, client_id, specialist_id,
    date_start, date_end, duration_minutes, break_minutes,
    status, final_price, notes, cancel_reason,
    created_at, updated_at, client_package_id, service_package_id
FROM bookings;

DROP TABLE bookings;
ALTER TABLE bookings_new RENAME TO bookings;

PRAGMA foreign_keys=ON;
