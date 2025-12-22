import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


# ======================================================
# ENV
# ======================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TG_ID = os.getenv("ADMIN_TG_ID")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Default Company")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if not ADMIN_TG_ID:
    raise RuntimeError("ADMIN_TG_ID is not set")

ADMIN_TG_ID = int(ADMIN_TG_ID)


# ======================================================
# DB URL PARSER (SQLite only)
# ======================================================

def get_sqlite_db_path(database_url: str) -> Path:
    """
    Supports:
      sqlite:///./data/sqlite/booking.db
      sqlite:////abs/path/to/booking.db
    """
    parsed = urlparse(database_url)

    if parsed.scheme != "sqlite":
        raise RuntimeError("init_admin supports only sqlite DATABASE_URL")

    if not parsed.path:
        raise RuntimeError("Invalid sqlite DATABASE_URL")

    raw_path = parsed.path

    # sqlite:///./path or sqlite:///../path  → relative to CWD
    if raw_path.startswith("/./") or raw_path.startswith("/../"):
        return (Path.cwd() / raw_path[1:]).resolve()

    # sqlite:////abs/path → absolute
    return Path(raw_path).resolve()


# ======================================================
# RESOLVE DB PATH (GLOBAL!)
# ======================================================

DB_PATH = get_sqlite_db_path(DATABASE_URL)

if not DB_PATH.exists():
    raise RuntimeError(f"Database file not found: {DB_PATH}")


# ======================================================
# DB UTILS
# ======================================================

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def audit(cur, event_type, actor_user_id=None, target_user_id=None, payload=None):
    """
    actor_user_id is NULL for bootstrap events
    """
    cur.execute(
        """
        INSERT INTO audit_log (event_type, actor_user_id, target_user_id, payload)
        VALUES (?, ?, ?, ?)
        """,
        (event_type, actor_user_id, target_user_id, payload),
    )


# ======================================================
# MAIN LOGIC
# ======================================================

def main():
    conn = get_conn()
    cur = conn.cursor()

    # --- ensure company ---
    cur.execute("SELECT id FROM company LIMIT 1")
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO company (name) VALUES (?)",
            (COMPANY_NAME,)
        )
        company_id = cur.lastrowid
    else:
        company_id = row["id"]

    # --- admin role ---
    cur.execute("SELECT id FROM roles WHERE name = 'admin'")
    role_row = cur.fetchone()
    if not role_row:
        raise RuntimeError("Role 'admin' not found in roles table")

    admin_role_id = role_row["id"]

    # --- users count ---
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    users_count = cur.fetchone()["cnt"]

    # --- find user by tg_id ---
    cur.execute(
        "SELECT id FROM users WHERE tg_id = ?",
        (ADMIN_TG_ID,)
    )
    user = cur.fetchone()

    # ==================================================
    # CASE 1: FIRST USER
    # ==================================================
    if users_count == 0:
        cur.execute(
            """
            INSERT INTO users (company_id, first_name, tg_id)
            VALUES (?, ?, ?)
            """,
            (company_id, "Admin", ADMIN_TG_ID)
        )
        user_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO user_roles (user_id, role_id)
            VALUES (?, ?)
            """,
            (user_id, admin_role_id)
        )

        audit(
            cur,
            event_type="bootstrap:first_admin_created",
            target_user_id=user_id,
            payload=f"tg_id={ADMIN_TG_ID}"
        )

        print(f"[BOOTSTRAP] First admin created (tg_id={ADMIN_TG_ID})")

    # ==================================================
    # CASE 2: USERS EXIST
    # ==================================================
    else:
        if not user:
            cur.execute(
                """
                INSERT INTO users (company_id, first_name, tg_id)
                VALUES (?, ?, ?)
                """,
                (company_id, "Admin", ADMIN_TG_ID)
            )
            user_id = cur.lastrowid

            cur.execute(
                """
                INSERT INTO user_roles (user_id, role_id)
                VALUES (?, ?)
                """,
                (user_id, admin_role_id)
            )

            audit(
                cur,
                event_type="bootstrap:admin_added",
                target_user_id=user_id,
                payload=f"tg_id={ADMIN_TG_ID}"
            )

            print(f"[BOOTSTRAP] New admin added (tg_id={ADMIN_TG_ID})")
            print("[BOOTSTRAP] Existing admins will be notified via audit")

        else:
            cur.execute(
                """
                SELECT 1
                FROM user_roles
                WHERE user_id = ? AND role_id = ?
                """,
                (user["id"], admin_role_id)
            )
            role_exists = cur.fetchone()

            if not role_exists:
                cur.execute(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    VALUES (?, ?)
                    """,
                    (user["id"], admin_role_id)
                )

                audit(
                    cur,
                    event_type="bootstrap:admin_role_granted",
                    target_user_id=user["id"],
                    payload=f"tg_id={ADMIN_TG_ID}"
                )

                print(f"[BOOTSTRAP] Admin role granted (tg_id={ADMIN_TG_ID})")

            else:
                print("[BOOTSTRAP] Admin already exists, nothing to do")

    conn.commit()
    conn.close()


# ======================================================
# ENTRYPOINT
# ======================================================

if __name__ == "__main__":
    main()

