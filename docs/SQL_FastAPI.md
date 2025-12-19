# SQL-схемы к FastAPI с предсказуемыми миграциями и явными роутами

> **Цель**: Получить точные SQLAlchemy-модели, синхронизированные с реальной PostgreSQL-схемой, используя SQLite как промежуточный слой, и подключить Alembic без риска перезаписи структуры.
> **Принципы**: схема — источник истины, минимализм, отсутствие ORM-магии, явные роуты, полный контроль над миграциями.

---

# Ключевой принцип системы записи:
1. База создаёт структуру
2. ORM отражает всю её геометрию
3. Pydantic ограничивает, что позволено API
4. API-роуты работают ТОЛЬКО с Pydantic
5. ORM и Pydantic никогда не смешиваются напрямую
6. Движение всегда одностороннее: ORM → Pydantic

##  Общая логика

1. **Схема PostgreSQL → чистый SQL** (без PSQL-специфики)
2. **SQL → SQLite-база** (временная, только для генерации)
3. **SQLite → ORM-модели** через `sqlacodegen`
4. **Скрипт миграций** — только отслеживает изменения
5. **Pydantic** - схемы
5. **FastAPI-роуты — явные, без generic-магии**, с чётким разделением: ORM ↔ Pydantic ↔ API

---

# Экспортировать схему PostgreSQL в чистый SQL

Только DDL (без данных и привязок к PSQL):

```bash
pg_dump -s -U your_user -h localhost your_db > schema_psql.sql
```

Преобразуй `schema_psql.sql` в `schema_sqlite.sql`, заменив:

- `SERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`
- `UUID` → `TEXT`
- `JSONB` / `JSON` → `TEXT`
- Удали `CREATE EXTENSION`, `nextval()`, `::regclass`, `OWNER TO`, `COMMENT ON`
- Убедись, что все типы совместимы с SQLite

Результат: **чистый, валидный SQL-файл**, понятный SQLite.

---

# Создать временный SQLite-файл

```bash
sqlite3 booking.db < schema_sqlite.sql
```

Теперь `booking.db` содержит точную структуру таблиц, соответствующую твоей PostgreSQL-схеме.

> ⚠️ Этот файл — временный артефакт. Не коммить в Git.

---

# Сгенерировать ORM-модели

ORM = полное описание таблиц
(все поля, FK, типы, nullable, defaults)
ORM — это карта базы данных внутри Python.

Установи зависимости:

```bash
pip install sqlalchemy sqlacodegen
```

Сгенерировать модели:

```bash
sqlacodegen sqlite:///booking.db --outfile app/models/generated.py
```

Результат — файл `app/models/generated.py` с:

- Точными именами таблиц и колонок
- Корректными первичными и внешними ключами
- SQLAlchemy-совместимыми типами

Это **каноническая ORM-модель**, порождённая схемой, а не наоборот.

---


# Будущие изменения: безопасные миграции

1. Не ствить alembic - этот костыль должен отслеживать миграции, но только тратит время. Работа не предсказуема! Требует живой БД для autogenerate.
2. Добавляем таблицу миграций
```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```
3. Каталог миграций
```plain
migrations/
   001_init.sql
   002_add_index.sql
   003_add_table_packages.sql
``` 
4. Скрипт мигратора (Python или Bash):

- читает schema_migrations
- находит все .sql файлы, версия которых > текущей
-  применяет их по очереди
- :пишет новую версию
Теперь ORM и БД всегда в синхроне, а миграции — предсказуемы.

---

# Создание роутов — явно, минималистично, без магии

## Принципы
- Никаких generic CRUD-фабрик
- Явные функции для каждого эндпоинта
- Чёткое разделение: ORM ↔ Pydantic ↔ FastAPI
- Легко расширять и тестировать

---

## Pydantic-схемы (`app/schemas.py`)

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class BookingBase(BaseModel):
user_id: int
room_id: int
start_time: datetime
end_time: datetime

class BookingCreate(BookingBase):
pass

class BookingUpdate(BaseModel):
start_time: Optional[datetime] = None
end_time: Optional[datetime] = None

class Booking(BookingBase):
id: int

class Config:
from_attributes = True
```

> Для множества таблиц — создавай схемы вручную или напиши простой генератор. Контроль важнее автоматизации.

---

## Настрой подключение к БД (`app/database.py`)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# В продакшене — только PostgreSQL
SQLALCHEMY_DATABASE_URL = "postgresql://user:pass@localhost/your_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
db = SessionLocal()
try:
yield db
finally:
db.close()
```

---

## Создание явных роутов (`app/api/v1/bookings.py`)

⚠️ ВАЖНО

Ниже приведён ТЕХНИЧЕСКИЙ ПРИМЕР структуры FastAPI-роутов.
Он показывает ТОЛЬКО:
- организацию кода
- работу с SQLAlchemy
- связь ORM ↔ Pydantic

❗ СПИСОК РАЗРЕШЁННЫХ HTTP-МЕТОДОВ
ОПРЕДЕЛЯЕТСЯ ИСКЛЮЧИТЕЛЬНО файлом `API.md`.

Если метод отсутствует в `API.md` —  
его НЕЛЬЗЯ реализовывать, даже если он есть в примере ниже.


```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models.generated import Booking as DBBooking
from app.schemas import Booking, BookingCreate, BookingUpdate
from app.database import get_db

router = APIRouter(prefix="/bookings", tags=["bookings"])

@router.get("/", response_model=List[Booking])
def read_bookings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
return db.query(DBBooking).offset(skip).limit(limit).all()

@router.get("/{booking_id}", response_model=Booking)
def read_booking(booking_id: int, db: Session = Depends(get_db)):
db_booking = db.query(DBBooking).filter(DBBooking.id == booking_id).first()
if not db_booking:
raise HTTPException(status_code=404, detail="Booking not found")
return db_booking

@router.post("/", response_model=Booking, status_code=201)
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
db_booking = DBBooking(**booking.dict())
db.add(db_booking)
db.commit()
db.refresh(db_booking)
return db_booking

@router.patch("/{booking_id}", response_model=Booking)
def update_booking(booking_id: int, booking: BookingUpdate, db: Session = Depends(get_db)):
db_booking = db.query(DBBooking).filter(DBBooking.id == booking_id).first()
if not db_booking:
raise HTTPException(status_code=404, detail="Booking not found")
for key, value in booking.dict(exclude_unset=True).items():
if value is not None:
setattr(db_booking, key, value)
db.commit()
db.refresh(db_booking)
return db_booking

@router.delete("/{booking_id}", status_code=204)
def delete_booking(booking_id: int, db: Session = Depends(get_db)):
db_booking = db.query(DBBooking).filter(DBBooking.id == booking_id).first()
if not db_booking:
raise HTTPException(status_code=404, detail="Booking not found")
db.delete(db_booking)
db.commit()
```

---

###  Подключение роутов в приложение (`app/main.py`)

```python
from fastapi import FastAPI
from app.api.v1.bookings import router as bookings_router

app = FastAPI(title="Booking API")
app.include_router(bookings_router)
```

---

## 🧪 Результат

- **ORM-модели** — 100% соответствуют схеме
- **Alembic** — не создаёт таблиц, только отслеживает изменения
- **SQLite** — используется только для генерации, не влияет на продакшен
- **PostgreSQL** — единственная БД в продакшене
- **Роуты** — явные, читаемые, без скрытой логики
- **Миграции** — предсказуемые, проверяемые, безопасные

---


