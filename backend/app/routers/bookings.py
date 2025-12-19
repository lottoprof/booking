# backend/app/routers/bookings.py
# API.md: PATCH = 405, DELETE = 405

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Bookings as DBBookings
from ..schemas.bookings import (
    BookingCreate,
    BookingRead,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/", response_model=list[BookingRead])
def list_bookings(db: Session = Depends(get_db)):
    return db.query(DBBookings).all()


@router.get("/{id}", response_model=BookingRead)
def get_booking(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBBookings, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(
    data: BookingCreate,
    db: Session = Depends(get_db),
):
    obj = DBBookings(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}")
def patch_not_allowed():
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed",
    )


@router.delete("/{id}")
def delete_not_allowed():
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed",
    )

