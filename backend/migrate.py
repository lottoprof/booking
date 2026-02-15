import sqlite3
import glob
import importlib.util
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

    conn.close()

    # Ищем миграции (.sql и .py)
    sql_files = glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))
    py_files = glob.glob(os.path.join(MIGRATIONS_DIR, "*.py"))
    files = sorted(sql_files + py_files)

    for path in files:
        filename = os.path.basename(path)
        version = int(filename.split("_")[0])

        if version > current_version:
            print(f"Applying migration {filename}...")

            if path.endswith(".py"):
                os.environ["DB_PATH"] = DB_PATH
                spec = importlib.util.spec_from_file_location(f"migration_{version}", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.run()
            else:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                with open(path, "r", encoding="utf-8") as f:
                    sql = f.read()
                cur.executescript(sql)
                cur.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
                conn.commit()
                conn.close()

            print(f"✔ Applied {filename}")

    print("All migrations applied.")

if __name__ == "__main__":
    apply_migrations()

