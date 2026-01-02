# backend/app/routers/rooms.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..models.generated import Rooms as DBRooms
from ..schemas.rooms import (
    RoomCreate,
    RoomUpdate,
    RoomRead,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("/", response_model=list[RoomRead])
def list_rooms(db: Session = Depends(get_db)):
    return (
        db.query(DBRooms)
        .filter(DBRooms.is_active == 1)
        .all()
    )


@router.get("/{id}", response_model=RoomRead)
def get_room(id: int, db: Session = Depends(get_db)):
    obj = (
        db.query(DBRooms)
        .filter(DBRooms.id == id, DBRooms.is_active == 1)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
def create_room(
    data: RoomCreate,
    db: Session = Depends(get_db),
):
    obj = DBRooms(**data.model_dump())
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Room with this name already exists in the location"
        )
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=RoomRead)
def update_room(
    id: int,
    data: RoomUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBRooms, id)
    if not obj or obj.is_active == 0:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Room with this name already exists in the location"
        )

    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBRooms, id)
    if not obj or obj.is_active == 0:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()

