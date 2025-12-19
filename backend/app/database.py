from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from .config import settings

# Создание движка SQLite
# check_same_thread=False — обязательно для работы SQLite из разных потоков FastAPI
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
)

# Включение поддержки внешних ключей в SQLite
@event.listens_for(engine, "connect")
def enable_sqlite_fk(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# SessionLocal — основной способ работы с БД
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Dependency для FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

