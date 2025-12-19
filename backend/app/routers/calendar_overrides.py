# backend/app/routers/calendar_overrides.py
# API.md: PATCH = 405, DELETE = ALLOWED (hard)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import CalendarOverrides as DBCalendarOverrides
from ..schemas.calendar_overrides import (
    CalendarOverrideCreate,
    CalendarOverrideRead,
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
    db.delete(obj)
    db.commit()

