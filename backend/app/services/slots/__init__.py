# backend/app/services/slots/__init__.py
"""
Slots calculation module.

Level 1: Base location slots (cached in Redis Sorted Sets)
Level 2: Service availability (calculated on-the-fly)
"""

from .config import BookingConfig, get_booking_config
from .calculator import calculate_day_slots
from .redis_store import SlotsRedisStore
from .invalidator import invalidate_location_cache
from .availability import calculate_service_availability

__all__ = [
    "BookingConfig",
    "get_booking_config",
    "calculate_day_slots",
    "SlotsRedisStore",
    "invalidate_location_cache",
    "calculate_service_availability",
]
