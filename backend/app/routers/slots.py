# backend/app/routers/slots.py
"""
Slots API endpoints.

Level 1: GET /slots/calendar - Calendar of available days for location
Level 2: GET /slots/day - Detailed slots for a day (service-specific)
"""

from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..redis_client import redis_client
from ..schemas.slots import (
    CalendarResponse,
    DayAvailability,
    DaySlotsResponse,
)
from ..services.slots import (
    BookingConfig,
    get_booking_config,
    calculate_location_grid,
    SlotsRedisStore,
)
from ..services.slots.calculator import count_open_slots, has_any_open_slot
from ..services.slots.availability import calculate_service_availability


router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("/calendar", response_model=CalendarResponse)
def get_slots_calendar(
    location_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    """
    Get calendar of available days for a location (Level 1).
    
    Returns list of days with availability status.
    Uses base grid - shows if location is open.
    """
    config = get_booking_config()
    store = SlotsRedisStore(redis_client, config)
    
    today = date.today()
    if start_date is None:
        start_date = today
    if end_date is None:
        end_date = start_date + timedelta(days=config.horizon_days)
    
    # Validate dates
    if start_date < today:
        start_date = today
    if end_date > today + timedelta(days=config.horizon_days):
        end_date = today + timedelta(days=config.horizon_days)
    if end_date < start_date:
        end_date = start_date
    
    # Generate date range
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    
    # Batch get cached grids
    cached_grids = store.mget_grids(location_id, dates)
    
    # Calculate missing grids
    grids_to_cache = {}
    days = []
    
    for dt in dates:
        grid = cached_grids.get(dt)
        
        if grid is None:
            grid = calculate_location_grid(db, location_id, dt, config)
            grids_to_cache[dt] = grid
        
        days.append(DayAvailability(
            date=dt.isoformat(),
            weekday=dt.weekday(),
            is_available=has_any_open_slot(grid),
            open_slots_count=count_open_slots(grid),
        ))
    
    # Batch cache calculated grids
    if grids_to_cache:
        store.mset_grids(location_id, grids_to_cache)
    
    return CalendarResponse(
        location_id=location_id,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        days=days,
        horizon_days=config.horizon_days,
        min_advance_hours=config.min_advance_hours,
    )


@router.get("/day", response_model=DaySlotsResponse)
def get_slots_day(
    location_id: int,
    service_id: int,
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    """
    Get available time slots for a service on a specific day (Level 2).
    
    Returns list of available start times with specialists who can provide
    the service at each time.
    
    Args:
        location_id: Location ID
        service_id: Service ID  
        date: Target date (YYYY-MM-DD)
    """
    config = get_booking_config()
    
    # Validate date is within horizon
    today = date.today()
    max_date = today + timedelta(days=config.horizon_days)
    
    if target_date < today:
        raise HTTPException(
            status_code=400,
            detail="Date cannot be in the past"
        )
    
    if target_date > max_date:
        raise HTTPException(
            status_code=400,
            detail=f"Date cannot be more than {config.horizon_days} days ahead"
        )
    
    # Calculate service availability (Level 2)
    result = calculate_service_availability(
        db=db,
        location_id=location_id,
        service_id=service_id,
        target_date=target_date,
        config=config,
    )
    
    return DaySlotsResponse(**result)


@router.get("/grid")
def get_slots_grid(
    location_id: int,
    target_date: date = Query(..., alias="date"),
    force_recalc: bool = False,
    db: Session = Depends(get_db),
):
    """
    Get raw grid for location and date (admin/debug endpoint).
    """
    config = get_booking_config()
    store = SlotsRedisStore(redis_client, config)
    
    cached = False
    grid = None
    
    if not force_recalc:
        grid = store.get_grid(location_id, target_date)
        cached = grid is not None
    
    if grid is None:
        grid = calculate_location_grid(db, location_id, target_date, config)
        store.set_grid(location_id, target_date, grid)
    
    version = store.get_version(location_id)
    
    return {
        "location_id": location_id,
        "date": target_date.isoformat(),
        "grid": grid,
        "cached": cached,
        "version": version,
        "slots_per_day": config.slots_per_day,
    }


@router.post("/invalidate")
def invalidate_slots_cache(
    location_id: int,
    dates: list[date] | None = None,
):
    """
    Manually invalidate slots cache for location (admin endpoint).
    """
    from ..services.slots import invalidate_location_cache
    
    deleted = invalidate_location_cache(redis_client, location_id, dates)
    
    return {
        "location_id": location_id,
        "deleted_keys": deleted,
        "dates": [d.isoformat() for d in dates] if dates else "all",
    }

