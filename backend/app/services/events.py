"""
backend/app/services/events.py

Event emitter: pushes events to Redis queues for consumption by gateway/bot.

Two queues:
- events:p2p — instant delivery (booking notifications to specific users)
- events:broadcast — throttled delivery (mass notifications)
"""

import json
import time
import logging

from ..redis_client import redis_client

logger = logging.getLogger(__name__)


def emit_event(event_type: str, payload: dict) -> None:
    """
    Emit a p2p event (instant delivery).

    Pushed to Redis list `events:p2p` for the consumer loop.
    """
    event = {
        "type": event_type,
        **payload,
        "ts": int(time.time()),
    }
    try:
        redis_client.rpush("events:p2p", json.dumps(event))
        logger.info(f"Event emitted: {event_type} → events:p2p")
    except Exception as e:
        logger.error(f"Failed to emit event {event_type}: {e}")


def emit_broadcast(event_type: str, payload: dict) -> None:
    """
    Emit a broadcast event (throttled delivery, 30 msg/sec).

    Pushed to Redis list `events:broadcast` for the consumer loop.
    """
    event = {
        "type": event_type,
        **payload,
        "ts": int(time.time()),
    }
    try:
        redis_client.rpush("events:broadcast", json.dumps(event))
        logger.info(f"Broadcast emitted: {event_type} → events:broadcast")
    except Exception as e:
        logger.error(f"Failed to emit broadcast {event_type}: {e}")
