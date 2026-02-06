# gateway/app/routers/web_booking.py
"""
Web booking API endpoints (Redis only, no SQL access).

These endpoints are for the public website booking flow.
All data is read from/written to Redis only.
A trusted consumer processes pending bookings → SQL via Backend internal API.

Security model:
- Web UI → Gateway → Redis only (untrusted)
- Consumer → Backend API → SQL (trusted, localhost only)
"""

import json
import logging
from datetime import date, datetime, timedelta
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..redis_client import redis_client
from ..config import DOMAIN_API_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web", tags=["web-booking"])


# ──────────────────────────────────────────────────────────────────────────────
# Redis keys
# ──────────────────────────────────────────────────────────────────────────────

CACHE_SERVICES_KEY = "cache:web:services"
CACHE_SPECIALISTS_KEY = "cache:web:specialists"
CACHE_LOCATIONS_KEY = "cache:web:locations"
CACHE_TTL = 300  # 5 minutes

SLOT_RESERVE_PREFIX = "slot_reserve"  # slot_reserve:{location_id}:{date}:{time}:{uuid}
SLOT_RESERVE_TTL = 300  # 5 minutes

PENDING_BOOKING_PREFIX = "pending_booking"  # pending_booking:{uuid}
PENDING_BOOKING_TTL = 3600  # 1 hour


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────────────

class WebService(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    duration_min: int
    price: float


class WebSpecialist(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    photo_url: Optional[str] = None


class WebLocation(BaseModel):
    id: int
    name: str
    address: Optional[str] = None


class WebDayStatus(BaseModel):
    date: str  # YYYY-MM-DD
    has_slots: bool
    open_slots_count: int = 0


class WebCalendarResponse(BaseModel):
    location_id: int
    days: list[WebDayStatus]


class WebTimeSlot(BaseModel):
    time: str  # HH:MM
    available: bool = True
    specialists: list[WebSpecialist] = []


class WebDaySlotsResponse(BaseModel):
    location_id: int
    service_id: int
    date: str
    slots: list[WebTimeSlot]


class SlotReserveRequest(BaseModel):
    location_id: int
    service_id: int
    specialist_id: Optional[int] = None
    date: str  # YYYY-MM-DD
    time: str  # HH:MM


class SlotReserveResponse(BaseModel):
    uuid: str
    expires_in: int = Field(description="Seconds until reservation expires")


class WebBookingRequest(BaseModel):
    reserve_uuid: str = Field(description="UUID from POST /web/reserve")
    phone: str = Field(description="Client phone number")
    name: Optional[str] = Field(None, description="Client name")


class PendingBookingResponse(BaseModel):
    uuid: str
    status: str = Field(description="pending | processing | confirmed | failed")
    booking_id: Optional[int] = None
    error: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

async def _fetch_and_cache_from_backend(
    endpoint: str,
    cache_key: str,
    ttl: int = CACHE_TTL
) -> list[dict]:
    """
    Fetch data from Backend API and cache in Redis.
    Used for services, specialists, locations.
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{DOMAIN_API_URL}{endpoint}",
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            # Cache in Redis
            redis_client.setex(cache_key, ttl, json.dumps(data))
            return data

    except Exception as e:
        logger.error(f"Failed to fetch from backend {endpoint}: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


def _get_cached_or_empty(cache_key: str) -> list[dict] | None:
    """Get cached data from Redis or return None on miss."""
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Services
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/services", response_model=list[WebService])
async def get_services():
    """
    Get list of available services.

    Reads from Redis cache, fetches from Backend on cache miss.
    """
    # Try cache first
    cached = _get_cached_or_empty(CACHE_SERVICES_KEY)
    if cached is not None:
        return [
            WebService(
                id=s["id"],
                name=s["name"],
                description=s.get("description"),
                category=s.get("category"),
                duration_min=s["duration_min"],
                price=s["price"]
            )
            for s in cached
            if s.get("is_active", True)
        ]

    # Cache miss - fetch from backend
    data = await _fetch_and_cache_from_backend("/services", CACHE_SERVICES_KEY)
    return [
        WebService(
            id=s["id"],
            name=s["name"],
            description=s.get("description"),
            category=s.get("category"),
            duration_min=s["duration_min"],
            price=s["price"]
        )
        for s in data
        if s.get("is_active", True)
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Specialists
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/specialists", response_model=list[WebSpecialist])
async def get_specialists(service_id: Optional[int] = None):
    """
    Get list of specialists, optionally filtered by service.

    Reads from Redis cache, fetches from Backend on cache miss.
    """
    # Try cache first
    cached = _get_cached_or_empty(CACHE_SPECIALISTS_KEY)
    if cached is None:
        # Cache miss - fetch from backend
        cached = await _fetch_and_cache_from_backend("/specialists", CACHE_SPECIALISTS_KEY)

    specialists = [
        WebSpecialist(
            id=s["id"],
            name=s.get("display_name") or f"Specialist {s['id']}",
            description=s.get("description"),
            photo_url=s.get("photo_url")
        )
        for s in cached
        if s.get("is_active", True)
    ]

    # TODO: Filter by service_id if provided (requires specialist_services data)

    return specialists


# ──────────────────────────────────────────────────────────────────────────────
# Locations
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/locations", response_model=list[WebLocation])
async def get_locations():
    """
    Get list of active locations.

    Reads from Redis cache, fetches from Backend on cache miss.
    """
    cached = _get_cached_or_empty(CACHE_LOCATIONS_KEY)
    if cached is None:
        cached = await _fetch_and_cache_from_backend("/locations", CACHE_LOCATIONS_KEY)

    return [
        WebLocation(
            id=loc["id"],
            name=loc["name"],
            address=loc.get("address")
        )
        for loc in cached
        if loc.get("is_active", True)
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Slots - Calendar (Level 1)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/slots/calendar", response_model=WebCalendarResponse)
async def get_slots_calendar(
    location_id: int,
    service_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Get calendar of available days for booking.

    Reads from Redis Level 1 cache (slots:day:{location_id}:{date}).
    """
    today = date.today()
    horizon_days = 30  # Default horizon

    if start_date:
        start = date.fromisoformat(start_date)
        if start < today:
            start = today
    else:
        start = today

    if end_date:
        end = date.fromisoformat(end_date)
        if end > today + timedelta(days=horizon_days):
            end = today + timedelta(days=horizon_days)
    else:
        end = start + timedelta(days=horizon_days)

    days = []
    current = start
    now_ts = datetime.now().timestamp()

    while current <= end:
        key = f"slots:day:{location_id}:{current.isoformat()}"

        # Count available slots (score > now_ts)
        if redis_client.exists(key):
            count = redis_client.zcount(key, now_ts, "+inf")
            days.append(WebDayStatus(
                date=current.isoformat(),
                has_slots=count > 0,
                open_slots_count=count
            ))
        else:
            # Cache miss - mark as unknown (has_slots=False for now)
            # The frontend should request specific day to trigger calculation
            days.append(WebDayStatus(
                date=current.isoformat(),
                has_slots=False,
                open_slots_count=0
            ))

        current += timedelta(days=1)

    return WebCalendarResponse(location_id=location_id, days=days)


# ──────────────────────────────────────────────────────────────────────────────
# Slots - Day (Level 2 simplified)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/slots/day", response_model=WebDaySlotsResponse)
async def get_slots_day(
    location_id: int,
    service_id: int,
    target_date: str = Query(..., alias="date"),
    specialist_id: Optional[int] = None,
):
    """
    Get available time slots for a specific day.

    Reads from Redis cache, excludes reserved slots.
    For full availability with specialist info, proxies to Backend.
    """
    import httpx

    # Fetch from Backend for accurate Level 2 calculation
    try:
        async with httpx.AsyncClient() as client:
            params = {
                "location_id": location_id,
                "service_id": service_id,
                "date": target_date,
            }
            response = await client.get(
                f"{DOMAIN_API_URL}/slots/day",
                params=params,
                timeout=10.0
            )

            if response.status_code != 200:
                # Fallback to empty if backend unavailable
                return WebDaySlotsResponse(
                    location_id=location_id,
                    service_id=service_id,
                    date=target_date,
                    slots=[]
                )

            data = response.json()

    except Exception as e:
        logger.error(f"Failed to fetch slots from backend: {e}")
        return WebDaySlotsResponse(
            location_id=location_id,
            service_id=service_id,
            date=target_date,
            slots=[]
        )

    # Get reserved slots to exclude
    reserved_times = set()
    reserve_pattern = f"{SLOT_RESERVE_PREFIX}:{location_id}:{target_date}:*"
    for key in redis_client.scan_iter(reserve_pattern):
        # key format: slot_reserve:{location_id}:{date}:{time}:{uuid}
        parts = key.split(":") if isinstance(key, str) else key.decode().split(":")
        if len(parts) >= 4:
            reserved_times.add(parts[3])  # time part

    # Build response, excluding reserved slots
    slots = []
    for time_slot in data.get("available_times", []):
        time_str = time_slot["time"]

        # Skip if this time is reserved by someone else
        if time_str in reserved_times:
            continue

        specialists = [
            WebSpecialist(
                id=sp["id"],
                name=sp["name"],
                description=None,
                photo_url=None
            )
            for sp in time_slot.get("specialists", [])
        ]

        # Filter by specialist if requested
        if specialist_id:
            specialists = [sp for sp in specialists if sp.id == specialist_id]
            if not specialists:
                continue

        slots.append(WebTimeSlot(
            time=time_str,
            available=True,
            specialists=specialists
        ))

    return WebDaySlotsResponse(
        location_id=location_id,
        service_id=service_id,
        date=target_date,
        slots=slots
    )


# ──────────────────────────────────────────────────────────────────────────────
# Slot Reservation
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/reserve", response_model=SlotReserveResponse)
async def create_slot_reserve(data: SlotReserveRequest):
    """
    Reserve a time slot temporarily (5 minutes).

    Prevents double-booking while client enters contact info.
    """
    # Validate date is not in past
    try:
        slot_date = date.fromisoformat(data.date)
        if slot_date < date.today():
            raise HTTPException(status_code=400, detail="Cannot reserve slots in the past")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    # Check if slot is already reserved
    check_pattern = f"{SLOT_RESERVE_PREFIX}:{data.location_id}:{data.date}:{data.time}:*"
    existing = list(redis_client.scan_iter(check_pattern))
    if existing:
        raise HTTPException(status_code=409, detail="Slot already reserved")

    # Create reservation
    reserve_uuid = str(uuid4())
    reserve_key = f"{SLOT_RESERVE_PREFIX}:{data.location_id}:{data.date}:{data.time}:{reserve_uuid}"

    reserve_data = {
        "location_id": data.location_id,
        "service_id": data.service_id,
        "specialist_id": data.specialist_id,
        "date": data.date,
        "time": data.time,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

    redis_client.setex(reserve_key, SLOT_RESERVE_TTL, json.dumps(reserve_data))

    logger.info(f"Slot reserved: {reserve_key}")

    return SlotReserveResponse(uuid=reserve_uuid, expires_in=SLOT_RESERVE_TTL)


@router.delete("/reserve/{uuid}")
async def cancel_slot_reserve(uuid: str):
    """
    Cancel a slot reservation.
    """
    # Find and delete the reservation
    pattern = f"{SLOT_RESERVE_PREFIX}:*:*:*:{uuid}"
    keys = list(redis_client.scan_iter(pattern))

    if not keys:
        raise HTTPException(status_code=404, detail="Reservation not found")

    for key in keys:
        redis_client.delete(key)

    logger.info(f"Slot reservation cancelled: {uuid}")

    return {"status": "cancelled"}


# ──────────────────────────────────────────────────────────────────────────────
# Pending Booking
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/booking", response_model=PendingBookingResponse)
async def create_pending_booking(data: WebBookingRequest):
    """
    Create a pending booking from a slot reservation.

    The booking is stored in Redis and processed asynchronously
    by the trusted consumer → Backend internal API.
    """
    # Find the reservation
    pattern = f"{SLOT_RESERVE_PREFIX}:*:*:*:{data.reserve_uuid}"
    keys = list(redis_client.scan_iter(pattern))

    if not keys:
        raise HTTPException(status_code=404, detail="Reservation not found or expired")

    reserve_key = keys[0] if isinstance(keys[0], str) else keys[0].decode()
    reserve_data = redis_client.get(reserve_key)

    if not reserve_data:
        raise HTTPException(status_code=404, detail="Reservation not found or expired")

    reserve = json.loads(reserve_data)

    # Create pending booking
    booking_uuid = str(uuid4())
    booking_key = f"{PENDING_BOOKING_PREFIX}:{booking_uuid}"

    pending_data = {
        "location_id": reserve["location_id"],
        "service_id": reserve["service_id"],
        "specialist_id": reserve.get("specialist_id"),
        "date": reserve["date"],
        "time": reserve["time"],
        "phone": data.phone,
        "name": data.name,
        "status": "pending",
        "error": None,
        "booking_id": None,
        "reserve_uuid": data.reserve_uuid,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

    redis_client.setex(booking_key, PENDING_BOOKING_TTL, json.dumps(pending_data))

    logger.info(f"Pending booking created: {booking_uuid}")

    return PendingBookingResponse(
        uuid=booking_uuid,
        status="pending"
    )


@router.get("/booking/{uuid}", response_model=PendingBookingResponse)
async def get_booking_status(uuid: str):
    """
    Get status of a pending booking.

    Used for polling until status is 'confirmed' or 'failed'.
    """
    key = f"{PENDING_BOOKING_PREFIX}:{uuid}"
    data = redis_client.get(key)

    if not data:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking = json.loads(data)

    return PendingBookingResponse(
        uuid=uuid,
        status=booking["status"],
        booking_id=booking.get("booking_id"),
        error=booking.get("error")
    )
