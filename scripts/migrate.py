import sqlite3
import glob
import os

DB_PATH = os.path.join("data", "sqlite", "booking.db")
MIGRATIONS_DIR = os.path.join("backend", "migrations")

def apply_migrations():
    print(f"Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Таблица версий миграций
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Текущая версия
    cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations;")
    current_version = cur.fetchone()[0]
    print(f"Current schema version: {current_version}")

    # Ищем миграции
    files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))

    for path in files:
        filename = os.path.basename(path)
        version = int(filename.split("_")[0])

        if version > current_version:
            print(f"Applying migration {filename}...")

            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()

            cur.executescript(sql)
            cur.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            conn.commit()

            print(f"✔ Applied {filename}")

    conn.close()
    print("All migrations applied.")

if __name__ == "__main__":
    apply_migrations()

