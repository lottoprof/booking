# backend/app/routers/service_packages.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import ServicePackages as DBServicePackages
from ..schemas.service_packages import (
    ServicePackageCreate,
    ServicePackageUpdate,
    ServicePackageRead,
)
from ..services.web_cache import invalidate_services_cache

router = APIRouter(prefix="/service_packages", tags=["service_packages"])


@router.get("/", response_model=list[ServicePackageRead])
def list_service_packages(db: Session = Depends(get_db)):
    return (
        db.query(DBServicePackages)
        .filter(DBServicePackages.is_active == 1)
        .all()
    )


@router.get("/{id}", response_model=ServicePackageRead)
def get_service_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServicePackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=ServicePackageRead, status_code=status.HTTP_201_CREATED
)
def create_service_package(
    data: ServicePackageCreate,
    db: Session = Depends(get_db),
):
    obj = DBServicePackages(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    invalidate_services_cache()
    return obj


@router.patch("/{id}", response_model=ServicePackageRead)
def update_service_package(
    id: int,
    data: ServicePackageUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBServicePackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    invalidate_services_cache()
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServicePackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()
    invalidate_services_cache()

