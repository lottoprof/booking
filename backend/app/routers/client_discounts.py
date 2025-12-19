# backend/app/routers/client_discounts.py
# API.md: PATCH = ALLOWED, DELETE = ALLOWED (hard)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import ClientDiscounts as DBClientDiscounts
from ..schemas.client_discounts import (
    ClientDiscountCreate,
    ClientDiscountUpdate,
    ClientDiscountRead,
)

router = APIRouter(prefix="/client_discounts", tags=["client_discounts"])


@router.get("/", response_model=list[ClientDiscountRead])
def list_client_discounts(db: Session = Depends(get_db)):
    return db.query(DBClientDiscounts).all()


@router.get("/{id}", response_model=ClientDiscountRead)
def get_client_discount(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBClientDiscounts, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=ClientDiscountRead, status_code=status.HTTP_201_CREATED
)
def create_client_discount(
    data: ClientDiscountCreate,
    db: Session = Depends(get_db),
):
    obj = DBClientDiscounts(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=ClientDiscountRead)
def update_client_discount(
    id: int,
    data: ClientDiscountUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBClientDiscounts, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_discount(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBClientDiscounts, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()

