# backend/app/routers/slots.py
"""
Slots API endpoints.

Level 1: GET /slots/calendar - Calendar of available days for location
Level 2: GET /slots/day - Detailed slots for a day (service-specific)
"""

from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..redis_client import redis_client
from ..schemas.slots import (
    SlotsCalendarResponse,
    SlotsDayStatus,
    SlotsDayResponse,
    SlotsGridResponse,
    SlotDebugEntry,
)
from ..services.slots import (
    BookingConfig,
    get_booking_config,
    calculate_day_slots,
    SlotsRedisStore,
)
from ..services.slots.availability import calculate_service_availability


router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("/calendar", response_model=SlotsCalendarResponse)
def get_slots_calendar(
    location_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    """Get calendar of available days for a location (Level 1)."""
    config = get_booking_config()
    store = SlotsRedisStore(redis_client, config)
    now = datetime.now()

    today = date.today()
    if start_date is None:
        start_date = today
    if end_date is None:
        end_date = start_date + timedelta(days=config.horizon_days)

    if start_date < today:
        start_date = today
    if end_date > today + timedelta(days=config.horizon_days):
        end_date = today + timedelta(days=config.horizon_days)
    if end_date < start_date:
        end_date = start_date

    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    # Batch check cached counts
    cached_counts = store.mget_counts(location_id, dates, now)
    days_to_calc: dict[date, list[tuple[str, float]]] = {}

    days = []
    for dt in dates:
        count = cached_counts.get(dt)

        if count is None:
            # Cache miss — calculate
            slots = calculate_day_slots(db, location_id, dt, config, now)
            days_to_calc[dt] = slots
            count = len([t for t, exp in slots if exp > now.timestamp()])

        days.append(SlotsDayStatus(
            date=dt,
            has_slots=count > 0,
            open_slots_count=count,
        ))

    # Store calculated days in batch
    if days_to_calc:
        store.store_multiple_days(location_id, days_to_calc)

    return SlotsCalendarResponse(
        location_id=location_id,
        start_date=start_date,
        end_date=end_date,
        days=days,
        horizon_days=config.horizon_days,
        min_advance_hours=config.min_advance_hours,
        slot_step_minutes=config.slot_step_minutes,
    )


@router.get("/day", response_model=SlotsDayResponse)
def get_slots_day(
    location_id: int,
    service_id: int | None = None,
    service_package_id: int | None = None,
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    """Get available time slots for a service/preset on a specific day (Level 2)."""
    if not service_id and not service_package_id:
        raise HTTPException(status_code=400, detail="service_id or service_package_id required")

    config = get_booking_config()

    today = date.today()
    max_date = today + timedelta(days=config.horizon_days)

    if target_date < today:
        raise HTTPException(status_code=400, detail="Date cannot be in the past")

    if target_date > max_date:
        raise HTTPException(status_code=400, detail=f"Date cannot be more than {config.horizon_days} days ahead")

    result = calculate_service_availability(
        db=db,
        location_id=location_id,
        service_id=service_id,
        target_date=target_date,
        config=config,
        redis=redis_client,
        service_package_id=service_package_id,
    )

    return SlotsDayResponse(**result)


@router.get("/grid", response_model=SlotsGridResponse)
def get_slots_grid(
    location_id: int,
    target_date: date = Query(..., alias="date"),
    force_recalc: bool = False,
    db: Session = Depends(get_db),
):
    """Get sorted set debug view for location and date (admin/debug endpoint)."""
    config = get_booking_config()
    store = SlotsRedisStore(redis_client, config)
    now = datetime.now()

    cached = False
    slot_data: list[tuple[str, float]] | None = None

    if not force_recalc:
        slot_data = store.get_all_slots_with_scores(location_id, target_date)
        cached = slot_data is not None

    if slot_data is None:
        slots = calculate_day_slots(db, location_id, target_date, config, now)
        store.store_day_slots(location_id, target_date, slots)
        slot_data = slots

    debug_slots = [
        SlotDebugEntry(
            time=time_str,
            expires_at=datetime.fromtimestamp(expire_ts),
        )
        for time_str, expire_ts in slot_data
    ]

    return SlotsGridResponse(
        location_id=location_id,
        date=target_date,
        slots=debug_slots,
        total_slots=len(debug_slots),
        cached=cached,
    )


@router.post("/invalidate")
def invalidate_slots_cache(
    location_id: int,
    dates: list[date] | None = None,
):
    """Manually invalidate slots cache for location (admin endpoint)."""
    from ..services.slots import invalidate_location_cache

    deleted = invalidate_location_cache(redis_client, location_id, dates)

    return {
        "location_id": location_id,
        "deleted_keys": deleted,
        "dates": [d.isoformat() for d in dates] if dates else "all",
    }
