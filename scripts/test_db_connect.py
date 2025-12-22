import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.generated import Company


def main():
    db = SessionLocal()
    try:
        print("DB OK:", db.execute(text("SELECT 1")).scalar())
        print("Companies:", len(db.query(Company).all()))
    finally:
        db.close()


if __name__ == "__main__":
    main()

