# backend/app/routers/booking_discounts.py
# API.md: PATCH = 405, DELETE = 405

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import BookingDiscounts as DBBookingDiscounts
from ..schemas.booking_discounts import (
    BookingDiscountCreate,
    BookingDiscountRead,
)

router = APIRouter(prefix="/booking_discounts", tags=["booking_discounts"])


@router.get("/", response_model=list[BookingDiscountRead])
def list_booking_discounts(db: Session = Depends(get_db)):
    return db.query(DBBookingDiscounts).all()


@router.get("/{id}", response_model=BookingDiscountRead)
def get_booking_discount(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBBookingDiscounts, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=BookingDiscountRead, status_code=status.HTTP_201_CREATED
)
def create_booking_discount(
    data: BookingDiscountCreate,
    db: Session = Depends(get_db),
):
    obj = DBBookingDiscounts(**data.model_dump())
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

