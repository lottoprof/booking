# SQL-схемы к FastAPI с предсказуемыми миграциями и явными роутами

> **Цель**: Получить точные SQLAlchemy-модели, синхронизированные с реальной PostgreSQL-схемой, используя SQLite как промежуточный слой, и подключить Alembic без риска перезаписи структуры.
> **Принципы**: схема — источник истины, минимализм, отсутствие ORM-магии, явные роуты, полный контроль над миграциями.

---

##  Общая логика

1. **Схема PostgreSQL → чистый SQL** (без PSQL-специфики)
2. **SQL → SQLite-база** (временная, только для генерации)
3. **SQLite → ORM-модели** через `sqlacodegen`
4. **Alembic инициализирован, но не создаёт таблиц** — только отслеживает изменения
5. **FastAPI-роуты — явные, без generic-магии**, с чётким разделением: ORM ↔ Pydantic ↔ API

---

## 📌 Шаг A — Экспортировать схему PostgreSQL в чистый SQL

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

## 📌 Шаг B — Создать временный SQLite-файл

```bash
sqlite3 booking.db < schema_sqlite.sql
```

Теперь `booking.db` содержит точную структуру таблиц, соответствующую твоей PostgreSQL-схеме.

> ⚠️ Этот файл — временный артефакт. Не коммить в Git.

---

## 📌 Шаг C — Сгенерировать ORM-модели

Установи зависимости:

```bash
pip install sqlalchemy sqlacodegen
```

Сгенерируй модели:

```bash
sqlacodegen sqlite:///booking.db --outfile app/models/generated.py
```

Результат — файл `app/models/generated.py` с:

- Точными именами таблиц и колонок
- Корректными первичными и внешними ключами
- SQLAlchemy-совместимыми типами

Это **каноническая ORM-модель**, порождённая схемой, а не наоборот.

---

## 📌 Шаг D — Инициализировать Alembic

```bash
pip install alembic
alembic init alembic
```

Настрой `alembic.ini` (указывай **PostgreSQL**, не SQLite):

```ini
sqlalchemy.url = postgresql://user:pass@localhost/your_db
```

В `alembic/env.py` подключи модели:

```python
from app.models.generated import Base
target_metadata = Base.metadata
```

---

## 📌 Шаг E — Пометить текущую схему как актуальную

Создай **пустую** миграцию:

```bash
alembic revision -m "init from existing schema" --empty
```

Проставь метку в PostgreSQL:

```bash
alembic stamp head
```

→ Alembic теперь **считает, что структура БД актуальна**.
→ Никакие `CREATE TABLE` не будут выполнены.
→ Ты **не ломаешь существующую БД**.

---

## 📌 Шаг F — Будущие изменения: безопасные миграции

1. Обнови `schema_sqlite.sql` вручную (отрази изменения из PSQL)
2. Пересоздай `booking.db`:
 ```bash
 sqlite3 booking.db < schema_sqlite.sql
 ```
3. Перегенерируй модели:
 ```bash
 sqlacodegen sqlite:///booking.db --outfile app/models/generated.py
 ```
4. Сгенерируй миграцию:
 ```bash
 alembic revision --autogenerate -m "add X to Y"
 ```
5. **Внимательно проверь SQL в миграции**
6. Примени:
 ```bash
 alembic upgrade head
 ```

Теперь ORM и БД всегда в синхроне, а миграции — предсказуемы.

---

## 🌐 Создание роутов — явно, минималистично, без магии

### Принципы
- Никаких generic CRUD-фабрик
- Явные функции для каждого эндпоинта
- Чёткое разделение: ORM ↔ Pydantic ↔ FastAPI
- Легко расширять и тестировать

---

### 1. Создай Pydantic-схемы (`app/schemas.py`)

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

### 2. Настрой подключение к БД (`app/database.py`)

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

### 3. Напиши явные роуты (`app/api/v1/bookings.py`)

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

### 4. Подключи роуты в приложение (`app/main.py`)

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


