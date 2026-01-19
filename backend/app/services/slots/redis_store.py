# backend/app/services/slots/redis_store.py
"""
Redis storage for slots grids.

Key format: slots:location:{location_id}:{date}
Value format: String of 96 characters "0"/"1"
"""

from datetime import date
from redis import Redis

from .config import BookingConfig, get_booking_config


class SlotsRedisStore:
    """
    Redis storage wrapper for location grids.
    """
    
    KEY_PREFIX = "slots:location"
    VERSION_PREFIX = "slots:location:version"
    
    def __init__(self, redis: Redis, config: BookingConfig | None = None):
        self.redis = redis
        self.config = config or get_booking_config()
    
    def _grid_key(self, location_id: int, dt: date) -> str:
        """Generate Redis key for location grid."""
        return f"{self.KEY_PREFIX}:{location_id}:{dt.isoformat()}"
    
    def _version_key(self, location_id: int) -> str:
        """Generate Redis key for location version."""
        return f"{self.VERSION_PREFIX}:{location_id}"
    
    def get_grid(self, location_id: int, dt: date) -> str | None:
        """
        Get cached grid for location and date.
        
        Returns:
            Grid string (96 chars) or None if not cached.
        """
        key = self._grid_key(location_id, dt)
        return self.redis.get(key)
    
    def set_grid(self, location_id: int, dt: date, grid: str) -> None:
        """
        Cache grid for location and date.
        
        Args:
            location_id: Location ID
            dt: Date
            grid: Grid string (96 chars of "0"/"1")
        """
        key = self._grid_key(location_id, dt)
        self.redis.setex(key, self.config.cache_ttl_seconds, grid)
    
    def mget_grids(
        self, 
        location_id: int, 
        dates: list[date]
    ) -> dict[date, str | None]:
        """
        Batch get grids for multiple dates.
        
        Args:
            location_id: Location ID
            dates: List of dates
            
        Returns:
            Dict mapping date -> grid (or None if not cached)
        """
        if not dates:
            return {}
        
        keys = [self._grid_key(location_id, dt) for dt in dates]
        values = self.redis.mget(keys)
        
        return {dt: val for dt, val in zip(dates, values)}
    
    def mset_grids(
        self, 
        location_id: int, 
        grids: dict[date, str]
    ) -> None:
        """
        Batch set grids for multiple dates.
        
        Args:
            location_id: Location ID
            grids: Dict mapping date -> grid string
        """
        if not grids:
            return
        
        pipe = self.redis.pipeline()
        for dt, grid in grids.items():
            key = self._grid_key(location_id, dt)
            pipe.setex(key, self.config.cache_ttl_seconds, grid)
        pipe.execute()
    
    def delete_grids(
        self, 
        location_id: int, 
        dates: list[date] | None = None
    ) -> int:
        """
        Delete cached grids.
        
        Args:
            location_id: Location ID
            dates: List of specific dates, or None to delete all
            
        Returns:
            Number of deleted keys
        """
        if dates:
            keys = [self._grid_key(location_id, dt) for dt in dates]
        else:
            pattern = f"{self.KEY_PREFIX}:{location_id}:*"
            keys = self.redis.keys(pattern)
        
        if not keys:
            return 0
        
        return self.redis.delete(*keys)
    
    def get_version(self, location_id: int) -> int:
        """Get current cache version for location."""
        val = self.redis.get(self._version_key(location_id))
        return int(val) if val else 0
    
    def incr_version(self, location_id: int) -> int:
        """Increment cache version for location."""
        return self.redis.incr(self._version_key(location_id))
