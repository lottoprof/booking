# backend/app/services/slots/calculator.py
"""
Level 1: Base location slot calculation.

Produces per-slot data:
  (time_str "HH:MM", expire_ts float)

expire_ts = (slot_datetime − min_advance_hours).timestamp()
Redis filters with ZRANGEBYSCORE {now_ts} +inf — dead slots drop automatically.

Contains:
✓ work_schedule of location
✓ calendar_overrides of location
✓ min_advance_hours (baked into expire_ts)

Does NOT contain:
✗ Bookings (checked at Level 2)
✗ Specialists (checked at Level 2)
✗ Rooms (checked at Level 2)
"""

import json
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from .config import BookingConfig, get_booking_config, time_str_to_minutes, minutes_to_time_str


def calculate_day_slots(
    db: Session,
    location_id: int,
    target_date: date,
    config: BookingConfig | None = None,
    now: datetime | None = None,
) -> list[tuple[str, float]]:
    """
    Calculate slots for a location on a specific date.

    Returns:
        List of (time_str, expire_ts) pairs. Empty list = no slots.
    """
    config = config or get_booking_config()
    now = now or datetime.now()
    now_ts = now.timestamp()

    # Step 1: Get location
    location = _get_location(db, location_id)
    if not location:
        return []

    # Step 2: Check calendar overrides (day_off, block, etc.)
    overrides = _get_location_overrides(db, location_id, target_date)
    custom_intervals = None

    if overrides:
        for ovr in overrides:
            if ovr.override_kind == "day_off":
                return []
            # Check if override has custom hours in reason (e.g., "10:00-15:00")
            if ovr.reason and "-" in ovr.reason:
                parts = ovr.reason.split("-")
                if len(parts) == 2 and ":" in parts[0] and ":" in parts[1]:
                    custom_intervals = [[parts[0].strip(), parts[1].strip()]]
                    break

        # If override exists but no custom hours, block the day
        if custom_intervals is None:
            return []

    # Step 3: Get working intervals for the day
    if custom_intervals:
        intervals = custom_intervals
    else:
        try:
            schedule = json.loads(location.work_schedule) if location.work_schedule else {}
        except json.JSONDecodeError:
            schedule = {}
        intervals = _get_day_intervals(schedule, target_date)
    if not intervals:
        return []

    # Step 4: Generate slots with expire_ts
    step = config.slot_step_minutes
    slots: list[tuple[str, float]] = []

    for interval in intervals:
        if len(interval) != 2:
            continue

        start_min = time_str_to_minutes(interval[0])
        end_min = time_str_to_minutes(interval[1])

        t = start_min
        while t < end_min:
            time_str = minutes_to_time_str(t)
            slot_dt = datetime.combine(target_date, datetime.min.time()) + timedelta(minutes=t)
            expire_ts = (slot_dt - timedelta(hours=config.min_advance_hours)).timestamp()

            if expire_ts > now_ts:
                slots.append((time_str, expire_ts))

            t += step

    return slots


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_day_intervals(
    schedule: dict,
    target_date: date,
) -> list[list[str]]:
    """
    Extract working intervals for target_date from schedule.
    Supports both Format A and Format B.

    Returns list of intervals: [["09:00", "18:00"], ...]
    """
    weekday = target_date.weekday()  # 0 = Monday, 6 = Sunday

    # Format B: numeric keys "0", "1", etc.
    weekday_str = str(weekday)
    if weekday_str in schedule:
        intervals = schedule[weekday_str]
        if isinstance(intervals, list):
            return intervals
        return []

    # Format A: named keys "mon", "tue", etc.
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_name = day_names[weekday]

    if day_name in schedule:
        day_data = schedule[day_name]

        if day_data is None:
            return []

        if isinstance(day_data, dict):
            start = day_data.get("start")
            end = day_data.get("end")
            if start and end:
                return [[start, end]]

        if isinstance(day_data, list):
            return day_data

    return []


def _get_location(db: Session, location_id: int):
    """Get location by ID."""
    from ...models.generated import Locations
    return db.query(Locations).filter(Locations.id == location_id).first()


def _get_location_overrides(db: Session, location_id: int, target_date: date) -> list:
    """Get calendar overrides for location on specific date."""
    from ...models.generated import CalendarOverrides

    date_str = target_date.isoformat()

    return (
        db.query(CalendarOverrides)
        .filter(
            CalendarOverrides.target_type == "location",
            CalendarOverrides.target_id == location_id,
            CalendarOverrides.date_start <= date_str,
            CalendarOverrides.date_end >= date_str,
        )
        .all()
    )
