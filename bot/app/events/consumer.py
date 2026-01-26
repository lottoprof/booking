"""
Redis event consumer loops.

Two consumers:
- p2p_consumer_loop: instant delivery from events:p2p
- broadcast_consumer_loop: throttled delivery from events:broadcast (30 msg/sec)

Started as asyncio tasks in gateway lifespan.
"""

import asyncio
import json
import logging
import time

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BROADCAST_INTERVAL = 1.0 / 30  # 30 msg/sec


async def p2p_consumer_loop(redis_url: str) -> None:
    """
    Consume events from events:p2p (instant, no throttle).

    Uses BRPOP with 5s timeout to avoid busy-waiting.
    On failure, retries up to MAX_RETRIES, then moves to dead-letter queue.
    """
    r = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("p2p_consumer_loop started")

    try:
        while True:
            try:
                result = await r.brpop("events:p2p", timeout=5)
                if result is None:
                    continue

                _, raw = result
                await _process_event_safe(r, raw, "events:p2p:retry", "events:p2p:dead")

            except asyncio.CancelledError:
                logger.info("p2p_consumer_loop cancelled")
                raise
            except Exception:
                logger.exception("p2p_consumer_loop error, retrying in 2s")
                await asyncio.sleep(2)
    finally:
        await r.aclose()


async def broadcast_consumer_loop(redis_url: str) -> None:
    """
    Consume events from events:broadcast (throttled, 30 msg/sec).

    Uses BRPOP with 5s timeout. Sleeps between messages to maintain rate.
    """
    r = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("broadcast_consumer_loop started")

    try:
        while True:
            try:
                result = await r.brpop("events:broadcast", timeout=5)
                if result is None:
                    continue

                _, raw = result
                await _process_event_safe(
                    r, raw, "events:broadcast:retry", "events:broadcast:dead"
                )

                # Throttle: 30 msg/sec
                await asyncio.sleep(BROADCAST_INTERVAL)

            except asyncio.CancelledError:
                logger.info("broadcast_consumer_loop cancelled")
                raise
            except Exception:
                logger.exception("broadcast_consumer_loop error, retrying in 2s")
                await asyncio.sleep(2)
    finally:
        await r.aclose()


async def _process_event_safe(
    r: aioredis.Redis,
    raw: str,
    retry_queue: str,
    dead_queue: str,
) -> None:
    """
    Parse and process a single event with retry logic.

    On failure:
    - If attempts < MAX_RETRIES → push to retry queue
    - Otherwise → push to dead-letter queue
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in event queue: {raw[:200]}")
        await r.rpush(dead_queue, raw)
        return

    attempt = data.get("_attempt", 1)

    try:
        from bot.app.events import process_event
        await process_event(data)
    except Exception:
        logger.exception(
            f"Failed to process event type={data.get('type')} "
            f"(attempt {attempt}/{MAX_RETRIES})"
        )

        if attempt < MAX_RETRIES:
            data["_attempt"] = attempt + 1
            await r.rpush(retry_queue, json.dumps(data))
            logger.info(f"Event re-queued to {retry_queue} (attempt {attempt + 1})")
        else:
            await r.rpush(dead_queue, json.dumps(data))
            logger.warning(
                f"Event moved to dead-letter queue {dead_queue}: "
                f"type={data.get('type')}"
            )


async def retry_consumer_loop(redis_url: str) -> None:
    """
    Consume events from retry queues with backoff.

    Reads from events:p2p:retry and events:broadcast:retry,
    re-inserts them into the main queues after a brief delay.
    """
    r = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("retry_consumer_loop started")

    retry_queues = {
        "events:p2p:retry": "events:p2p",
        "events:broadcast:retry": "events:broadcast",
    }

    try:
        while True:
            try:
                moved = False
                for retry_q, main_q in retry_queues.items():
                    raw = await r.lpop(retry_q)
                    if raw:
                        await r.rpush(main_q, raw)
                        moved = True
                        logger.info(f"Retry: moved event from {retry_q} → {main_q}")

                if not moved:
                    await asyncio.sleep(5)

            except asyncio.CancelledError:
                logger.info("retry_consumer_loop cancelled")
                raise
            except Exception:
                logger.exception("retry_consumer_loop error, retrying in 5s")
                await asyncio.sleep(5)
    finally:
        await r.aclose()
