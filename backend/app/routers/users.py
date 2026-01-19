# backend/app/routers/users.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from urllib.parse import unquote

from ..database import get_db
from ..models.generated import Users as DBUsers
from ..schemas.users import (
    UserCreate,
    UserUpdate,
    UserRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return (
        db.query(DBUsers)
        .filter(DBUsers.is_active == 1)
        .all()
    )

@router.get("/by_tg/{tg_id}", response_model=UserRead)
def get_user_by_tg_id(tg_id: int, db: Session = Depends(get_db)):
    obj = (
        db.query(DBUsers)
        .filter(DBUsers.tg_id == tg_id, DBUsers.is_active == 1)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    return obj

@router.get("/by_phone/{phone}", response_model=UserRead)
def get_user_by_phone(phone: str, db: Session = Depends(get_db)):
    """
    Поиск пользователя по телефону.
    Возвращает пользователя независимо от is_active (для проверки деактивации).
    """
    # URL decode: %2B → +
    phone = unquote(phone)
    
    obj = (
        db.query(DBUsers)
        .filter(DBUsers.phone == phone)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    return obj

@router.get("/{id}", response_model=UserRead)
def get_user(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBUsers, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj

@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
):
    obj = DBUsers(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=UserRead)
def update_user(
    id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBUsers, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    update_data = data.model_dump(exclude_unset=True)
    
    # ==========================================================
    # MATCHING: imported_clients → users
    # Если пришёл phone — ищем в imported_clients
    # ==========================================================
    if "phone" in update_data and update_data["phone"]:
        phone = update_data["phone"]
        try:
            result = db.execute(
                text("""
                    SELECT id, first_name, last_name
                    FROM imported_clients
                    WHERE phone = :phone
                      AND matched_user_id IS NULL
                """),
                {"phone": phone}
            ).fetchone()
            
            if result:
                imported_id, imported_first, imported_last = result
                
                # Копируем имя/фамилию если есть
                if imported_first and "first_name" not in update_data:
                    update_data["first_name"] = imported_first
                if imported_last and "last_name" not in update_data:
                    update_data["last_name"] = imported_last
                
                # Помечаем как matched
                db.execute(
                    text("""
                        UPDATE imported_clients
                        SET matched_user_id = :user_id,
                            matched_at = :now
                        WHERE id = :id
                    """),
                    {
                        "user_id": id,
                        "now": datetime.utcnow().isoformat(),
                        "id": imported_id
                    }
                )
                logger.info(f"[MATCHING] imported_clients.id={imported_id} → users.id={id}")
                
        except Exception as e:
            # Таблицы нет или другая ошибка — продолжаем без matching
            logger.debug(f"[MATCHING] Skipped: {e}")
    
    # ==========================================================
    # Применяем изменения
    # ==========================================================
    for field, value in update_data.items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBUsers, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()

