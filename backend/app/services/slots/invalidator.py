# backend/app/services/slots/invalidator.py
"""
Cache invalidation for location slots.

Triggers:
✓ Location work_schedule changed → invalidate all dates
✓ Location calendar_override created/deleted → invalidate affected dates

Does NOT trigger:
✗ Booking created/cancelled (Level 2 calculates on-the-fly)
✗ Specialist schedule changed (Level 2)
✗ Room changes (Level 2)
"""

from datetime import date
from redis import Redis

from .redis_store import SlotsRedisStore


def invalidate_location_cache(
    redis: Redis,
    location_id: int,
    dates: list[date] | None = None,
) -> int:
    """
    Invalidate cached grids for location.
    
    Args:
        redis: Redis client
        location_id: Location ID
        dates: List of specific dates to invalidate,
               or None to invalidate all cached dates
    
    Returns:
        Number of deleted cache keys
    """
    store = SlotsRedisStore(redis)
    return store.delete_day_slots(location_id, dates)


def get_affected_dates(
    date_start: date,
    date_end: date,
) -> list[date]:
    """
    Get list of dates in range [date_start, date_end].
    
    Args:
        date_start: Start date (inclusive)
        date_end: End date (inclusive)
    
    Returns:
        List of dates
    """
    from datetime import timedelta
    
    if date_start > date_end:
        date_start, date_end = date_end, date_start
    
    dates = []
    current = date_start
    while current <= date_end:
        dates.append(current)
        current += timedelta(days=1)
    
    return dates


def get_affected_dates_from_override(override) -> list[date]:
    """
    Extract affected dates from calendar override object.
    
    Args:
        override: CalendarOverride object with date_start, date_end
    
    Returns:
        List of dates
    """
    from datetime import datetime
    
    # Parse dates (could be string or date)
    if isinstance(override.date_start, str):
        start = datetime.fromisoformat(override.date_start).date()
    else:
        start = override.date_start
    
    if isinstance(override.date_end, str):
        end = datetime.fromisoformat(override.date_end).date()
    else:
        end = override.date_end
    
    return get_affected_dates(start, end)
