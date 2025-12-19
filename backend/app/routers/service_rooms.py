# backend/app/routers/service_rooms.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import ServiceRooms as DBServiceRooms
from ..schemas.service_rooms import (
    ServiceRoomCreate,
    ServiceRoomUpdate,
    ServiceRoomRead,
)

router = APIRouter(prefix="/service_rooms", tags=["service_rooms"])


@router.get("/", response_model=list[ServiceRoomRead])
def list_service_rooms(db: Session = Depends(get_db)):
    return (
        db.query(DBServiceRooms)
        .filter(DBServiceRooms.is_active == 1)
        .all()
    )


@router.get("/{id}", response_model=ServiceRoomRead)
def get_service_room(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServiceRooms, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=ServiceRoomRead, status_code=status.HTTP_201_CREATED
)
def create_service_room(
    data: ServiceRoomCreate,
    db: Session = Depends(get_db),
):
    obj = DBServiceRooms(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=ServiceRoomRead)
def update_service_room(
    id: int,
    data: ServiceRoomUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBServiceRooms, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service_room(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServiceRooms, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()

