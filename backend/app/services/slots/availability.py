# backend/app/services/slots/availability.py
"""
Level 2: Service availability calculation.

Calculates available time slots for a specific service on a specific day.
Takes into account:
- Base location grid (Level 1)
- Specialists who provide the service
- Specialist schedules and overrides
- Existing bookings
- Rooms (if service requires room)
"""

import json
from datetime import date, datetime
from math import ceil
from sqlalchemy.orm import Session

from .config import BookingConfig, get_booking_config
from .calculator import calculate_location_grid, is_range_available


def calculate_service_availability(
    db: Session,
    location_id: int,
    service_id: int,
    target_date: date,
    config: BookingConfig | None = None,
) -> dict:
    """
    Calculate available time slots for a service.
    
    Args:
        db: Database session
        location_id: Location ID
        service_id: Service ID
        target_date: Date to check
        config: Booking configuration
    
    Returns:
        Dict with available times (for DaySlotsResponse)
    """
    config = config or get_booking_config()
    
    # Step 1: Get base location grid (Level 1)
    base_grid = calculate_location_grid(db, location_id, target_date, config)
    
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
    
    # Step 4: Calculate grid for each specialist
    specialist_grids = {}
    for spec in specialists:
        spec_grid = _calculate_specialist_grid(
            db, base_grid, spec, target_date, config
        )
        specialist_grids[spec.id] = {
            "grid": spec_grid,
            "name": spec.display_name or f"Specialist {spec.id}",
        }
    
    # Step 5: Find available start times
    available_times = []
    
    for slot_index in range(config.slots_per_day - slots_needed + 1):
        # Find specialists available for this slot range
        available_specialists = []
        
        for spec_id, spec_data in specialist_grids.items():
            if is_range_available(spec_data["grid"], slot_index, slots_needed):
                available_specialists.append({
                    "id": spec_id,
                    "name": spec_data["name"],
                })
        
        if available_specialists:
            time_str = config.format_slot_time(slot_index)
            available_times.append({
                "time": time_str,
                "slot_index": slot_index,
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


def _calculate_specialist_grid(
    db: Session,
    base_grid: str,
    specialist,
    target_date: date,
    config: BookingConfig,
) -> str:
    """
    Calculate availability grid for a specialist.
    
    Starts with base_grid and applies:
    - Specialist work_schedule
    - Specialist calendar_overrides
    - Specialist bookings
    """
    # Start with base grid (copy)
    grid = list(base_grid)
    
    # Apply specialist work_schedule
    if specialist.work_schedule:
        _apply_specialist_schedule(grid, specialist.work_schedule, target_date, config)
    
    # Apply specialist calendar_overrides
    overrides = _get_specialist_overrides(db, specialist.id, target_date)
    for override in overrides:
        _apply_override_to_grid(grid, override, config)
    
    # Apply specialist bookings
    bookings = _get_specialist_bookings(db, specialist.id, target_date)
    for booking in bookings:
        _apply_booking_to_grid(grid, booking, config)
    
    return "".join(grid)


def _apply_specialist_schedule(
    grid: list[str],
    work_schedule_json: str,
    target_date: date,
    config: BookingConfig,
) -> None:
    """Apply specialist's work schedule to grid."""
    try:
        schedule = json.loads(work_schedule_json) if work_schedule_json else {}
    except json.JSONDecodeError:
        schedule = {}
    
    if not schedule:
        # Empty schedule - specialist doesn't work
        for i in range(len(grid)):
            grid[i] = "0"
        return
    
    weekday = target_date.weekday()
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_name = day_names[weekday]
    weekday_str = str(weekday)
    
    # Get intervals for this day
    intervals = []
    
    # Format B: numeric keys
    if weekday_str in schedule:
        val = schedule[weekday_str]
        if isinstance(val, list):
            intervals = val
    # Format A: named keys
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
        # Day off for specialist
        for i in range(len(grid)):
            grid[i] = "0"
        return
    
    # Build set of working slots
    working_slots = set()
    for interval in intervals:
        if len(interval) != 2:
            continue
        start_slot = _time_to_slot(interval[0], config)
        end_slot = _time_to_slot(interval[1], config)
        for s in range(start_slot, end_slot):
            working_slots.add(s)
    
    # Close slots outside working hours
    for i in range(len(grid)):
        if i not in working_slots:
            grid[i] = "0"


def _apply_override_to_grid(
    grid: list[str],
    override,
    config: BookingConfig,
) -> None:
    """Apply calendar override to grid (closes all slots)."""
    for i in range(len(grid)):
        grid[i] = "0"


def _apply_booking_to_grid(
    grid: list[str],
    booking,
    config: BookingConfig,
) -> None:
    """Apply existing booking to grid (close occupied slots)."""
    # Parse booking start time
    try:
        if isinstance(booking.date_start, str):
            dt = datetime.fromisoformat(booking.date_start)
        else:
            dt = booking.date_start
        
        start_slot = config.time_to_slot(dt.hour, dt.minute)
        
        # Calculate slots needed for this booking
        duration = booking.duration_minutes or 60
        break_min = booking.break_minutes or 0
        total_min = duration + break_min
        slots_needed = ceil(total_min / config.slot_step_minutes)
        
        # Close slots
        for i in range(start_slot, min(start_slot + slots_needed, len(grid))):
            grid[i] = "0"
            
    except (ValueError, AttributeError):
        pass


def _time_to_slot(time_str: str, config: BookingConfig) -> int:
    """Convert "HH:MM" to slot index."""
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return config.time_to_slot(hour, minute)
    except (ValueError, IndexError):
        return 0


# Database helpers

def _get_service(db: Session, service_id: int):
    """Get service by ID."""
    from ...models.generated import Services
    return db.query(Services).filter(
        Services.id == service_id,
        Services.is_active == 1
    ).first()


def _get_service_specialists(db: Session, service_id: int) -> list:
    """Get active specialists who provide this service."""
    from ...models.generated import Specialists, SpecialistServices
    
    # Join through specialist_services
    results = (
        db.query(Specialists)
        .join(
            SpecialistServices,
            Specialists.id == SpecialistServices.specialist_id
        )
        .filter(
            SpecialistServices.service_id == service_id,
            SpecialistServices.is_active == 1,
            Specialists.is_active == 1,
        )
        .all()
    )
    
    return results


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

