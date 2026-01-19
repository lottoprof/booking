# backend/app/routers/calendar_overrides.py
# API.md: PATCH = 405, DELETE = ALLOWED (hard)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..redis_client import redis_client
from ..models.generated import CalendarOverrides as DBCalendarOverrides
from ..schemas.calendar_overrides import (
    CalendarOverrideCreate,
    CalendarOverrideRead,
)
from ..services.slots.invalidator import (
    invalidate_location_cache,
    get_affected_dates_from_override,
)

router = APIRouter(prefix="/calendar_overrides", tags=["calendar_overrides"])


@router.get("/", response_model=list[CalendarOverrideRead])
def list_calendar_overrides(db: Session = Depends(get_db)):
    return db.query(DBCalendarOverrides).all()


@router.get("/{id}", response_model=CalendarOverrideRead)
def get_calendar_override(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBCalendarOverrides, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=CalendarOverrideRead, status_code=status.HTTP_201_CREATED
)
def create_calendar_override(
    data: CalendarOverrideCreate,
    db: Session = Depends(get_db),
):
    obj = DBCalendarOverrides(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    
    # Invalidate slots cache for location overrides
    if obj.target_type == "location" and obj.target_id:
        dates = get_affected_dates_from_override(obj)
        invalidate_location_cache(redis_client, obj.target_id, dates)
    
    return obj


@router.patch("/{id}")
def patch_not_allowed():
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed",
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_override(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBCalendarOverrides, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Save info before deletion for cache invalidation
    target_type = obj.target_type
    target_id = obj.target_id
    affected_dates = None
    
    if target_type == "location" and target_id:
        affected_dates = get_affected_dates_from_override(obj)
    
    db.delete(obj)
    db.commit()
    
    # Invalidate slots cache for location overrides
    if target_type == "location" and target_id:
        invalidate_location_cache(redis_client, target_id, affected_dates)

