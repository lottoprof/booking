# backend/app/routers/users.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Users as DBUsers
from ..schemas.users import (
    UserCreate,
    UserUpdate,
    UserRead,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return (
        db.query(DBUsers)
        .filter(DBUsers.is_active == 1)
        .all()
    )


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

    for field, value in data.model_dump(exclude_unset=True).items():
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

