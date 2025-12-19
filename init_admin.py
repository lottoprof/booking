import os
import sqlite3
from pathlib import Path

DB_PATH = Path("data/sqlite/booking.db")

ADMIN_TG_ID = os.getenv("ADMIN_TG_ID")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Default Company")

if not ADMIN_TG_ID:
    raise RuntimeError("ADMIN_TG_ID is not set")

ADMIN_TG_ID = int(ADMIN_TG_ID)


def get_conn():
    return sqlite3.connect(DB_PATH)


def main():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
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

    # --- roles ---
    cur.execute("SELECT id FROM roles WHERE name='admin'")
    admin_role_id = cur.fetchone()["id"]

    # --- users count ---
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    users_count = cur.fetchone()["cnt"]

    # --- find user by tg_id ---
    cur.execute(
        "SELECT id FROM users WHERE tg_id=?",
        (ADMIN_TG_ID,)
    )
    user = cur.fetchone()

    if users_count == 0:
        # === FIRST USER ===
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

        print(f"[INIT] First admin created (tg_id={ADMIN_TG_ID})")

    else:
        # === USERS EXIST ===
        if not user:
            # create new admin
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

            print(f"[INIT] New admin added (tg_id={ADMIN_TG_ID})")
            print("[INIT] Existing admins should be notified")

        else:
            # ensure role exists
            cur.execute(
                """
                SELECT 1 FROM user_roles
                WHERE user_id=? AND role_id=?
                """,
                (user["id"], admin_role_id)
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    VALUES (?, ?)
                    """,
                    (user["id"], admin_role_id)
                )
                print(f"[INIT] Role admin added to existing user (tg_id={ADMIN_TG_ID})")
            else:
                print("[INIT] Admin already exists, nothing to do")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()

