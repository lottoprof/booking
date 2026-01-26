# backend/app/services/slots/redis_store.py
"""
Redis storage for slots using Sorted Sets.

Key format: slots:day:{location_id}:{date}
Value: Sorted Set where member = "HH:MM", score = expire_ts
       (unix timestamp when slot stops being available).

Query: ZRANGEBYSCORE key {now_ts} +inf → only live slots.
Sentinel: "__empty__" with score=0 marks "calculated, zero slots".
"""

from datetime import date, datetime
from redis import Redis

from .config import BookingConfig, get_booking_config


EMPTY_SENTINEL = "__empty__"


class SlotsRedisStore:
    """Redis storage wrapper using Sorted Sets for slot data."""

    KEY_PREFIX = "slots:day"

    def __init__(self, redis: Redis, config: BookingConfig | None = None):
        self.redis = redis
        self.config = config or get_booking_config()

    def _key(self, location_id: int, dt: date) -> str:
        return f"{self.KEY_PREFIX}:{location_id}:{dt.isoformat()}"

    # ── Write ────────────────────────────────────────────────────────────

    def store_day_slots(
        self,
        location_id: int,
        dt: date,
        slots: list[tuple[str, float]],
    ) -> None:
        """
        Store calculated slots for a day.

        Args:
            location_id: Location ID
            dt: Target date
            slots: List of (time_str, expire_ts) pairs.
                   Empty list → sentinel is stored.
        """
        key = self._key(location_id, dt)
        pipe = self.redis.pipeline()

        # Remove old data
        pipe.delete(key)

        if slots:
            mapping = {time_str: expire_ts for time_str, expire_ts in slots}
            pipe.zadd(key, mapping)
            max_expire = max(expire_ts for _, expire_ts in slots)
            # Key lives until the last slot expires + 1 minute buffer
            pipe.expireat(key, int(max_expire) + 60)
        else:
            # Empty day — sentinel so EXISTS returns True
            pipe.zadd(key, {EMPTY_SENTINEL: 0})
            end_of_day = datetime.combine(dt, datetime.max.time())
            pipe.expireat(key, int(end_of_day.timestamp()) + 60)

        pipe.execute()

    def store_multiple_days(
        self,
        location_id: int,
        days_slots: dict[date, list[tuple[str, float]]],
    ) -> None:
        """Batch store slots for multiple days via pipeline."""
        if not days_slots:
            return

        pipe = self.redis.pipeline()
        for dt, slots in days_slots.items():
            key = self._key(location_id, dt)
            pipe.delete(key)

            if slots:
                mapping = {time_str: expire_ts for time_str, expire_ts in slots}
                pipe.zadd(key, mapping)
                max_expire = max(expire_ts for _, expire_ts in slots)
                pipe.expireat(key, int(max_expire) + 60)
            else:
                pipe.zadd(key, {EMPTY_SENTINEL: 0})
                end_of_day = datetime.combine(dt, datetime.max.time())
                pipe.expireat(key, int(end_of_day.timestamp()) + 60)

        pipe.execute()

    # ── Read ─────────────────────────────────────────────────────────────

    def get_available_slots(
        self,
        location_id: int,
        dt: date,
        now: datetime,
    ) -> list[str] | None:
        """
        Get available (live) slots for a day.

        Returns:
            Sorted list of "HH:MM" strings, or None on cache miss.
        """
        key = self._key(location_id, dt)
        if not self.redis.exists(key):
            return None

        now_ts = now.timestamp()
        members = self.redis.zrangebyscore(key, now_ts, "+inf")
        return [
            m.decode() if isinstance(m, bytes) else m
            for m in members
            if (m.decode() if isinstance(m, bytes) else m) != EMPTY_SENTINEL
        ]

    def count_available(
        self,
        location_id: int,
        dt: date,
        now: datetime,
    ) -> int | None:
        """
        Count available slots for a day.

        Returns:
            Count of live slots, or None on cache miss.
        """
        key = self._key(location_id, dt)
        if not self.redis.exists(key):
            return None

        now_ts = now.timestamp()
        return self.redis.zcount(key, now_ts, "+inf")

    def mget_counts(
        self,
        location_id: int,
        dates: list[date],
        now: datetime,
    ) -> dict[date, int | None]:
        """
        Batch get slot counts for multiple dates.

        Returns:
            Dict mapping date → count (or None on cache miss).
        """
        if not dates:
            return {}

        now_ts = now.timestamp()
        keys = [self._key(location_id, dt) for dt in dates]

        # First pass: check existence
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.exists(key)
        exists_results = pipe.execute()

        # Second pass: count available for existing keys
        pipe = self.redis.pipeline()
        for key, exists in zip(keys, exists_results):
            if exists:
                pipe.zcount(key, now_ts, "+inf")
        count_results = pipe.execute()

        # Merge results
        result = {}
        count_idx = 0
        for dt, exists in zip(dates, exists_results):
            if exists:
                result[dt] = count_results[count_idx]
                count_idx += 1
            else:
                result[dt] = None

        return result

    # ── Delete ───────────────────────────────────────────────────────────

    def delete_day_slots(
        self,
        location_id: int,
        dates: list[date] | None = None,
    ) -> int:
        """
        Delete cached slots.

        Args:
            location_id: Location ID
            dates: Specific dates, or None to delete all for location.

        Returns:
            Number of deleted keys.
        """
        if dates:
            keys = [self._key(location_id, dt) for dt in dates]
        else:
            pattern = f"{self.KEY_PREFIX}:{location_id}:*"
            keys = self.redis.keys(pattern)

        if not keys:
            return 0

        return self.redis.delete(*keys)

    # ── Debug ────────────────────────────────────────────────────────────

    def get_all_slots_with_scores(
        self,
        location_id: int,
        dt: date,
    ) -> list[tuple[str, float]] | None:
        """
        Get all stored slots with their expire_ts (for debug endpoint).

        Returns:
            List of (time_str, expire_ts) or None on cache miss.
        """
        key = self._key(location_id, dt)
        if not self.redis.exists(key):
            return None

        raw = self.redis.zrangebyscore(key, "-inf", "+inf", withscores=True)
        return [
            (m.decode() if isinstance(m, bytes) else m, score)
            for m, score in raw
            if (m.decode() if isinstance(m, bytes) else m) != EMPTY_SENTINEL
        ]
