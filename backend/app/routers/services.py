# backend/app/routers/services.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Services as DBServices
from ..schemas.services import (
    ServiceCreate,
    ServiceUpdate,
    ServiceRead,
)

router = APIRouter(prefix="/services", tags=["services"])


@router.get("/", response_model=list[ServiceRead])
def list_services(db: Session = Depends(get_db)):
    return (
        db.query(DBServices)
        .filter(DBServices.is_active == 1)
        .all()
    )


@router.get("/{id}", response_model=ServiceRead)
def get_service(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServices, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    data: ServiceCreate,
    db: Session = Depends(get_db),
):
    obj = DBServices(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=ServiceRead)
def update_service(
    id: int,
    data: ServiceUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBServices, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServices, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()

