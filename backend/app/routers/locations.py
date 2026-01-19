# backend/app/routers/locations.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..redis_client import redis_client
from ..models.generated import Locations as DBLocations
from ..schemas.locations import (
    LocationCreate,
    LocationUpdate,
    LocationRead,
)
from ..services.slots.invalidator import invalidate_location_cache

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/", response_model=list[LocationRead])
def list_locations(db: Session = Depends(get_db)):
    return (
        db.query(DBLocations)
        .filter(DBLocations.is_active == 1)
        .all()
    )


@router.get("/{id}", response_model=LocationRead)
def get_location(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBLocations, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    data: LocationCreate,
    db: Session = Depends(get_db),
):
    obj = DBLocations(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=LocationRead)
def update_location(
    id: int,
    data: LocationUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBLocations, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    
    # Invalidate slots cache when work_schedule changes
    if "work_schedule" in changes:
        invalidate_location_cache(redis_client, id)
    
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBLocations, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()
    
    # Invalidate slots cache when location is deactivated
    invalidate_location_cache(redis_client, id)

