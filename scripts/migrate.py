import sqlite3
import glob
import os
import sys

# ---- project root ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))

DB_PATH = os.path.join(PROJECT_ROOT, "data", "sqlite", "booking.db")
DEFAULT_MIGRATIONS_DIR = os.path.join(PROJECT_ROOT, "backend", "migrations")

def apply_migrations(migrations_path=None):
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Using DB: {DB_PATH}")

    # гарантируем каталог БД
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations;")
    current_version = cur.fetchone()[0]
    print(f"Current schema version: {current_version}")

    # ---- выбираем миграции ----
    if migrations_path:
        path = os.path.abspath(migrations_path)
        if os.path.isdir(path):
            files = sorted(glob.glob(os.path.join(path, "*.sql")))
        else:
            files = [path]
    else:
        files = sorted(glob.glob(os.path.join(DEFAULT_MIGRATIONS_DIR, "*.sql")))

    for path in files:
        filename = os.path.basename(path)
        version = int(filename.split("_")[0])

        if version > current_version:
            print(f"Applying migration {filename}...")

            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()

            cur.executescript(sql)
            cur.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (version,)
            )
            conn.commit()

            print(f"✔ Applied {filename}")

    conn.close()
    print("All migrations applied.")

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    apply_migrations(arg)

