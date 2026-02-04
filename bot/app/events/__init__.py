"""
Bot event dispatcher.

Events arrive from Redis queues (pushed by backend).
Consumer loops in gateway process read the queues and call process_event().
"""

import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# Registry of event handlers
EVENT_HANDLERS: dict[str, Callable[[dict], Awaitable[None]]] = {}


def register_event(event_type: str):
    """Decorator to register an event handler."""
    def decorator(func: Callable[[dict], Awaitable[None]]):
        EVENT_HANDLERS[event_type] = func
        logger.info(f"Registered event handler: {event_type}")
        return func
    return decorator


async def process_event(data: dict) -> None:
    """
    Dispatch an event to its registered handler.

    Args:
        data: {"type": "event_type", ...payload}
    """
    event_type = data.get("type")

    if not event_type:
        logger.warning("Event without type field, skipping")
        return

    handler = EVENT_HANDLERS.get(event_type)

    if handler:
        logger.info(f"Processing event: {event_type}")
        await handler(data)
    else:
        logger.warning(f"No handler for event type: {event_type}")


# Import handlers to trigger registration via decorators
from . import booking  # noqa: E402, F401
from . import google_calendar  # noqa: E402, F401
