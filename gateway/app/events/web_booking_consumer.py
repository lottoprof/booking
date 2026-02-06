# gateway/app/events/web_booking_consumer.py
"""
Web booking consumer loop.

Processes pending bookings from Redis → Backend internal API → SQL.

This is a TRUSTED consumer running on the server (not exposed to web clients).
It reads pending bookings created by the public /web/booking endpoint
and creates actual bookings via the Backend internal API.

Flow:
1. Scan pending_booking:* keys with status=pending
2. Mark as processing (prevent double processing)
3. Call Backend POST /internal/bookings/from-web
4. Update status to confirmed (with booking_id) or failed (with error)
5. Delete the slot reservation

Started as asyncio task in gateway lifespan.
"""

import asyncio
import json
import logging
from datetime import datetime

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

PENDING_BOOKING_PREFIX = "pending_booking"
SLOT_RESERVE_PREFIX = "slot_reserve"
PENDING_BOOKING_TTL = 3600  # 1 hour (for confirmed bookings)


async def web_booking_consumer_loop(redis_url: str, backend_url: str) -> None:
    """
    Consume pending bookings from Redis and create them via Backend API.

    Scans for pending_booking:* keys every second.
    Processes one booking at a time to avoid race conditions.
    """
    r = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("web_booking_consumer_loop started")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            while True:
                try:
                    await _process_pending_bookings(r, client, backend_url)
                    await asyncio.sleep(1)

                except asyncio.CancelledError:
                    logger.info("web_booking_consumer_loop cancelled")
                    raise
                except Exception:
                    logger.exception("web_booking_consumer_loop error, retrying in 5s")
                    await asyncio.sleep(5)
        finally:
            await r.aclose()


async def _process_pending_bookings(
    r: aioredis.Redis,
    client: httpx.AsyncClient,
    backend_url: str,
) -> None:
    """Process all pending bookings."""
    # Scan for pending booking keys
    cursor = 0
    while True:
        cursor, keys = await r.scan(
            cursor=cursor,
            match=f"{PENDING_BOOKING_PREFIX}:*",
            count=100
        )

        for key in keys:
            await _process_single_booking(r, client, backend_url, key)

        if cursor == 0:
            break


async def _process_single_booking(
    r: aioredis.Redis,
    client: httpx.AsyncClient,
    backend_url: str,
    key: str,
) -> None:
    """Process a single pending booking."""
    raw = await r.get(key)
    if not raw:
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in pending booking: {key}")
        await r.delete(key)
        return

    # Only process pending bookings
    if data.get("status") != "pending":
        return

    booking_uuid = key.split(":")[-1]
    logger.info(f"Processing pending booking: {booking_uuid}")

    # Mark as processing (atomically)
    data["status"] = "processing"
    await r.setex(key, PENDING_BOOKING_TTL, json.dumps(data))

    try:
        # Call Backend internal API
        response = await client.post(
            f"{backend_url}/internal/bookings/from-web",
            json={
                "location_id": data["location_id"],
                "service_id": data["service_id"],
                "specialist_id": data.get("specialist_id"),
                "date": data["date"],
                "time": data["time"],
                "phone": data["phone"],
                "name": data.get("name"),
            }
        )

        if response.status_code == 201 or response.status_code == 200:
            result = response.json()

            # Success!
            data["status"] = "confirmed"
            data["booking_id"] = result.get("booking_id")
            data["client_id"] = result.get("client_id")
            data["confirmed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            logger.info(
                f"Booking confirmed: {booking_uuid} → booking_id={result.get('booking_id')}"
            )

            # Delete slot reservation
            await _delete_slot_reservation(r, data)

        else:
            # Backend returned error
            error_detail = "Unknown error"
            try:
                error_body = response.json()
                error_detail = error_body.get("detail", str(error_body))
            except Exception:
                error_detail = response.text[:200] if response.text else "No response"

            data["status"] = "failed"
            data["error"] = error_detail
            data["failed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            logger.warning(
                f"Booking failed: {booking_uuid} → {error_detail}"
            )

    except httpx.HTTPError as e:
        # Network/timeout error
        data["status"] = "failed"
        data["error"] = f"Network error: {str(e)}"
        data["failed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        logger.error(f"Booking network error: {booking_uuid} → {e}")

    except Exception as e:
        # Unexpected error
        data["status"] = "failed"
        data["error"] = f"Internal error: {str(e)}"
        data["failed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        logger.exception(f"Booking processing error: {booking_uuid}")

    # Save final status
    await r.setex(key, PENDING_BOOKING_TTL, json.dumps(data))


async def _delete_slot_reservation(r: aioredis.Redis, booking_data: dict) -> None:
    """Delete the slot reservation after successful booking."""
    reserve_uuid = booking_data.get("reserve_uuid")
    if not reserve_uuid:
        return

    location_id = booking_data["location_id"]
    booking_date = booking_data["date"]
    booking_time = booking_data["time"]

    # Pattern: slot_reserve:{location_id}:{date}:{time}:{uuid}
    reserve_key = f"{SLOT_RESERVE_PREFIX}:{location_id}:{booking_date}:{booking_time}:{reserve_uuid}"
    deleted = await r.delete(reserve_key)

    if deleted:
        logger.info(f"Deleted slot reservation: {reserve_key}")
