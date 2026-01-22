# backend/app/services/slots/config.py
"""
Booking configuration for slots calculation.
"""

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class BookingConfig:
    """
    Configuration for booking/slots system.
    
    Attributes:
        horizon_days: How many days ahead to show slots (30/60/90)
        min_advance_hours: Minimum hours before slot can be booked (1/6/12/24)
        slot_step_minutes: Base grid step in minutes (15/30/60)
        cache_ttl_seconds: Redis cache TTL for base grid
    """
    horizon_days: int = 60
    min_advance_hours: int = 12
    slot_step_minutes: int = 30  # 15 / 30 / 60
    cache_ttl_seconds: int = 86400  # 24 hours
    
    def __post_init__(self):
        """Validate configuration."""
        if self.slot_step_minutes not in (15, 30, 60):
            raise ValueError(f"slot_step_minutes must be 15, 30, or 60, got {self.slot_step_minutes}")
    
    @property
    def slots_per_day(self) -> int:
        """
        Number of slots in a day.
        
        - 15 min → 96 slots
        - 30 min → 48 slots
        - 60 min → 24 slots
        """
        return (24 * 60) // self.slot_step_minutes
    
    def time_to_slot(self, hour: int, minute: int) -> int:
        """Convert time to slot index."""
        total_minutes = hour * 60 + minute
        return total_minutes // self.slot_step_minutes
    
    def slot_to_time(self, slot: int) -> tuple[int, int]:
        """Convert slot index to (hour, minute)."""
        total_minutes = slot * self.slot_step_minutes
        return total_minutes // 60, total_minutes % 60
    
    def format_slot_time(self, slot: int) -> str:
        """Convert slot index to time string "HH:MM"."""
        hour, minute = self.slot_to_time(slot)
        return f"{hour:02d}:{minute:02d}"


@lru_cache
def get_booking_config() -> BookingConfig:
    """
    Get booking configuration (singleton).
    
    In the future, this can read from environment or database.
    """
    return BookingConfig()
