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
from ..services.package_pricing import enrich_package_price

router = APIRouter(prefix="/service_packages", tags=["service_packages"])


def _to_read(obj: DBServicePackages, db: Session) -> dict:
    """Convert DB object to read dict with computed package_price."""
    data = ServicePackageRead.model_validate(obj).model_dump()
    data["package_price"] = enrich_package_price(obj, db)
    return data


@router.get("/", response_model=list[ServicePackageRead])
def list_service_packages(db: Session = Depends(get_db)):
    packages = (
        db.query(DBServicePackages)
        .filter(DBServicePackages.is_active == 1)
        .all()
    )
    return [_to_read(p, db) for p in packages]


@router.get("/{id}", response_model=ServicePackageRead)
def get_service_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServicePackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_read(obj, db)


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
    return _to_read(obj, db)


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
    return _to_read(obj, db)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServicePackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()
    invalidate_services_cache()

