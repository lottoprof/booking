# backend/app/services/slots/calculator.py
"""
Level 1: Base location grid calculation.

Grid contains:
✓ work_schedule of location
✓ calendar_overrides of location
✓ min_advance_hours

Grid does NOT contain:
✗ Bookings (checked at Level 2)
✗ Specialists (checked at Level 2)
✗ Rooms (checked at Level 2)
"""

import json
from datetime import date, datetime, timedelta
from math import ceil
from sqlalchemy.orm import Session

from .config import BookingConfig, get_booking_config


def calculate_location_grid(
    db: Session,
    location_id: int,
    target_date: date,
    config: BookingConfig | None = None,
    now: datetime | None = None,
) -> str:
    """
    Calculate base grid for location on a specific date.
    
    Args:
        db: Database session
        location_id: Location ID
        target_date: Date to calculate grid for
        config: Booking configuration
        now: Current datetime (for testing, defaults to datetime.now())
    
    Returns:
        Grid string of 96 characters ("0" = closed, "1" = open)
    """
    config = config or get_booking_config()
    now = now or datetime.now()
    
    # Step 1: Initialize grid (all open)
    grid = ["1"] * config.slots_per_day
    
    # Step 2: Apply min_advance_hours (for today only)
    if target_date == now.date():
        _apply_min_advance(grid, now, config)
    
    # Step 3: Apply location work_schedule
    location = _get_location(db, location_id)
    if location:
        _apply_work_schedule(grid, location.work_schedule, target_date, config)
    else:
        # Location not found - close all slots
        return "0" * config.slots_per_day
    
    # Step 4: Apply calendar_overrides for location
    overrides = _get_location_overrides(db, location_id, target_date)
    for override in overrides:
        _apply_override(grid, override, config)
    
    return "".join(grid)


def _apply_min_advance(
    grid: list[str],
    now: datetime,
    config: BookingConfig,
) -> None:
    """
    Close slots before (now + min_advance_hours).
    Round up to next slot boundary.
    """
    cutoff = now + timedelta(hours=config.min_advance_hours)
    
    # Round up to next slot boundary
    minutes = cutoff.hour * 60 + cutoff.minute
    slot_minutes = config.slot_step_minutes
    rounded_minutes = ceil(minutes / slot_minutes) * slot_minutes
    
    cutoff_slot = rounded_minutes // slot_minutes
    
    # Close all slots before cutoff
    for i in range(min(cutoff_slot, len(grid))):
        grid[i] = "0"


def _apply_work_schedule(
    grid: list[str],
    work_schedule_json: str,
    target_date: date,
    config: BookingConfig,
) -> None:
    """
    Apply location work schedule.
    Close slots OUTSIDE working hours.
    
    Schedule format:
    {
        "0": [["09:00", "18:00"]],           # Monday
        "1": [["09:00", "12:00"], ["14:00", "20:00"]],  # Tuesday (with break)
        "6": []                              # Sunday (closed)
    }
    """
    try:
        schedule = json.loads(work_schedule_json) if work_schedule_json else {}
    except json.JSONDecodeError:
        schedule = {}
    
    weekday = str(target_date.weekday())
    day_intervals = schedule.get(weekday, [])
    
    if not day_intervals:
        # No working hours - close all slots
        for i in range(len(grid)):
            grid[i] = "0"
        return
    
    # Build a set of open slots from intervals
    open_slots = set()
    for interval in day_intervals:
        if len(interval) != 2:
            continue
        
        start_time, end_time = interval
        start_slot = _time_str_to_slot(start_time, config)
        end_slot = _time_str_to_slot(end_time, config)
        
        # Add all slots in interval [start, end)
        for slot in range(start_slot, end_slot):
            open_slots.add(slot)
    
    # Close slots not in working hours
    for i in range(len(grid)):
        if i not in open_slots:
            grid[i] = "0"


def _apply_override(
    grid: list[str],
    override,
    config: BookingConfig,
) -> None:
    """
    Apply calendar override (close slots for day_off, block, etc.).
    
    Override kinds that close slots:
    - day_off: whole day closed
    - block: whole day closed
    - cleaning: whole day closed
    - maintenance: whole day closed
    - admin_hold: whole day closed
    """
    # All current override kinds close the whole day
    for i in range(len(grid)):
        grid[i] = "0"


def _time_str_to_slot(time_str: str, config: BookingConfig) -> int:
    """
    Convert time string "HH:MM" to slot index.
    """
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return config.time_to_slot(hour, minute)
    except (ValueError, IndexError):
        return 0


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


# === Utility functions ===

def is_slot_open(grid: str, slot_index: int) -> bool:
    """Check if specific slot is open."""
    if 0 <= slot_index < len(grid):
        return grid[slot_index] == "1"
    return False


def is_range_available(grid: str, start_slot: int, num_slots: int) -> bool:
    """Check if a range of consecutive slots is available."""
    end_slot = start_slot + num_slots
    if end_slot > len(grid):
        return False
    return all(grid[i] == "1" for i in range(start_slot, end_slot))


def count_open_slots(grid: str) -> int:
    """Count number of open slots in grid."""
    return grid.count("1")


def has_any_open_slot(grid: str) -> bool:
    """Check if grid has at least one open slot."""
    return "1" in grid
