# backend/app/services/slots/availability.py
"""
Level 2: Service availability calculation.

Calculates available time slots for a specific service on a specific day.
Uses set[str] of "HH:MM" time strings instead of grid bit-arrays.

Takes into account:
- Base location slots (Level 1, cached in Redis Sorted Set)
- Specialists who provide the service
- Specialist schedules and overrides
- Existing bookings
"""

import json
from datetime import date, datetime
from math import ceil
from redis import Redis
from sqlalchemy.orm import Session

from .config import BookingConfig, get_booking_config, time_str_to_minutes, minutes_to_time_str
from .calculator import calculate_day_slots
from .redis_store import SlotsRedisStore


def calculate_service_availability(
    db: Session,
    location_id: int,
    service_id: int,
    target_date: date,
    config: BookingConfig | None = None,
    redis: Redis | None = None,
) -> dict:
    """
    Calculate available time slots for a service.

    Returns:
        Dict with available times (for SlotsDayResponse).
    """
    config = config or get_booking_config()
    now = datetime.now()

    # Step 1: Get base location slots (Level 1)
    base_times = _get_base_times(db, location_id, target_date, config, now, redis)

    # Step 2: Get service info
    service = _get_service(db, service_id)
    if not service:
        return {
            "location_id": location_id,
            "service_id": service_id,
            "date": target_date.isoformat(),
            "service_duration_min": 0,
            "slots_needed": 0,
            "available_times": [],
        }

    duration_min = service.duration_min
    break_min = service.break_min or 0
    total_min = duration_min + break_min
    slots_needed = ceil(total_min / config.slot_step_minutes)

    # Step 3: Get specialists for this service
    specialists = _get_service_specialists(db, service_id)
    if not specialists:
        return {
            "location_id": location_id,
            "service_id": service_id,
            "date": target_date.isoformat(),
            "service_duration_min": duration_min,
            "slots_needed": slots_needed,
            "available_times": [],
        }

    base_set = set(base_times)

    # Step 4: Build per-specialist available time sets
    specialist_times: dict[int, tuple[str, set[str]]] = {}
    for spec in specialists:
        times = set(base_set)

        # Intersect with specialist working times
        working = _get_specialist_working_times(
            spec.work_schedule, target_date, config
        )
        times &= working

        # Check specialist overrides
        overrides = _get_specialist_overrides(db, spec.id, target_date)
        if overrides:
            has_day_off = False
            custom_times = None

            for ovr in overrides:
                if ovr.override_kind == "day_off":
                    has_day_off = True
                    break
                # Check custom hours in reason (e.g., "10:00-14:00")
                if ovr.reason and "-" in ovr.reason:
                    parts = ovr.reason.split("-")
                    if len(parts) == 2 and ":" in parts[0] and ":" in parts[1]:
                        start_min = time_str_to_minutes(parts[0].strip())
                        end_min = time_str_to_minutes(parts[1].strip())
                        custom_times = set()
                        t = start_min
                        while t < end_min:
                            custom_times.add(minutes_to_time_str(t))
                            t += config.slot_step_minutes
                        break

            if has_day_off:
                times = set()
            elif custom_times is not None:
                times &= custom_times
            else:
                # Other override without custom hours - block all
                times = set()

        # Subtract booked times
        bookings = _get_specialist_bookings(db, spec.id, target_date)
        booked = _get_booked_times(bookings, config)
        times -= booked

        name = spec.display_name or f"Specialist {spec.id}"
        specialist_times[spec.id] = (name, times)

    # Step 5: Find available start times (need slots_needed consecutive)
    available_times = []
    step = config.slot_step_minutes

    for time_str in sorted(base_set):
        needed = _consecutive_times(time_str, slots_needed, step)
        if not needed:
            continue

        available_specialists = []
        for spec_id, (spec_name, spec_times) in specialist_times.items():
            if all(t in spec_times for t in needed):
                available_specialists.append({
                    "id": spec_id,
                    "name": spec_name,
                })

        if available_specialists:
            available_times.append({
                "time": time_str,
                "specialists": available_specialists,
            })

    return {
        "location_id": location_id,
        "service_id": service_id,
        "date": target_date.isoformat(),
        "service_duration_min": duration_min,
        "slots_needed": slots_needed,
        "available_times": available_times,
    }


# ── Base times (Level 1 with cache) ─────────────────────────────────────


def _get_base_times(
    db: Session,
    location_id: int,
    target_date: date,
    config: BookingConfig,
    now: datetime,
    redis: Redis | None,
) -> list[str]:
    """Get base location times, using Redis cache when available."""
    if redis is not None:
        store = SlotsRedisStore(redis, config)
        cached = store.get_available_slots(location_id, target_date, now)
        if cached is not None:
            return cached

        # Cache miss — calculate and store
        slots = calculate_day_slots(db, location_id, target_date, config, now)
        store.store_day_slots(location_id, target_date, slots)
        return [time_str for time_str, _ in slots]

    # No Redis — calculate on the fly
    slots = calculate_day_slots(db, location_id, target_date, config, now)
    return [time_str for time_str, _ in slots]


# ── Specialist helpers ───────────────────────────────────────────────────


def _get_specialist_working_times(
    work_schedule_json: str | None,
    target_date: date,
    config: BookingConfig,
) -> set[str]:
    """Get set of "HH:MM" times when specialist works on target_date."""
    try:
        schedule = json.loads(work_schedule_json) if work_schedule_json else {}
    except json.JSONDecodeError:
        schedule = {}

    if not schedule:
        return set()

    weekday = target_date.weekday()
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_name = day_names[weekday]
    weekday_str = str(weekday)

    # Get intervals (Format B then Format A)
    intervals: list = []
    if weekday_str in schedule:
        val = schedule[weekday_str]
        if isinstance(val, list):
            intervals = val
    elif day_name in schedule:
        val = schedule[day_name]
        if val is None:
            intervals = []
        elif isinstance(val, dict):
            start = val.get("start")
            end = val.get("end")
            if start and end:
                intervals = [[start, end]]
        elif isinstance(val, list):
            intervals = val

    if not intervals:
        return set()

    step = config.slot_step_minutes
    times: set[str] = set()
    for interval in intervals:
        if len(interval) != 2:
            continue
        start_min = time_str_to_minutes(interval[0])
        end_min = time_str_to_minutes(interval[1])
        t = start_min
        while t < end_min:
            times.add(minutes_to_time_str(t))
            t += step

    return times


def _get_booked_times(bookings: list, config: BookingConfig) -> set[str]:
    """Get set of "HH:MM" times occupied by existing bookings."""
    times: set[str] = set()
    step = config.slot_step_minutes

    for booking in bookings:
        try:
            if isinstance(booking.date_start, str):
                dt = datetime.fromisoformat(booking.date_start)
            else:
                dt = booking.date_start

            start_min = dt.hour * 60 + dt.minute
            duration = booking.duration_minutes or 60
            break_min = booking.break_minutes or 0
            total_min = duration + break_min
            slots_needed = ceil(total_min / step)

            for i in range(slots_needed):
                t = start_min + i * step
                times.add(minutes_to_time_str(t))
        except (ValueError, AttributeError):
            pass

    return times


def _consecutive_times(
    start_time: str,
    slots_needed: int,
    step: int,
) -> list[str]:
    """
    Generate list of consecutive time strings starting from start_time.

    Returns empty list if times would cross midnight (>= 24:00).
    """
    start_min = time_str_to_minutes(start_time)
    result = []
    for i in range(slots_needed):
        t = start_min + i * step
        if t >= 24 * 60:
            return []
        result.append(minutes_to_time_str(t))
    return result


# ── Database helpers ─────────────────────────────────────────────────────


def _get_service(db: Session, service_id: int):
    """Get service by ID."""
    from ...models.generated import Services
    return db.query(Services).filter(
        Services.id == service_id,
        Services.is_active == 1
    ).first()


def _get_service_specialists(db: Session, service_id: int) -> list:
    """Get active specialists who provide this service."""
    from ...models.generated import Specialists, t_specialist_services

    return (
        db.query(Specialists)
        .join(
            t_specialist_services,
            Specialists.id == t_specialist_services.c.specialist_id
        )
        .filter(
            t_specialist_services.c.service_id == service_id,
            t_specialist_services.c.is_active == 1,
            Specialists.is_active == 1,
        )
        .all()
    )


def _get_specialist_overrides(db: Session, specialist_id: int, target_date: date) -> list:
    """Get calendar overrides for specialist on date."""
    from ...models.generated import CalendarOverrides

    date_str = target_date.isoformat()

    return (
        db.query(CalendarOverrides)
        .filter(
            CalendarOverrides.target_type == "specialist",
            CalendarOverrides.target_id == specialist_id,
            CalendarOverrides.date_start <= date_str,
            CalendarOverrides.date_end >= date_str,
        )
        .all()
    )


def _get_specialist_bookings(db: Session, specialist_id: int, target_date: date) -> list:
    """Get active bookings for specialist on date."""
    from ...models.generated import Bookings
    from sqlalchemy import func

    date_str = target_date.isoformat()

    return (
        db.query(Bookings)
        .filter(
            Bookings.specialist_id == specialist_id,
            func.date(Bookings.date_start) == date_str,
            Bookings.status.in_(["pending", "confirmed"]),
        )
        .all()
    )
