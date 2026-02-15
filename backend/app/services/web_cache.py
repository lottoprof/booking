"""Write-through cache rebuild for gateway web endpoints."""

import logging

from sqlalchemy.orm import Session

from ..redis_client import redis_client
from .services_cache_builder import build_pricing_cards_json

logger = logging.getLogger(__name__)

_SERVICES_KEY_PREFIX = "cache:web:services"
_SPECIALISTS_KEY = "cache:web:specialists"
_LOCATIONS_KEY = "cache:web:locations"


def rebuild_services_cache(db: Session) -> None:
    """Build PricingCard JSON for both views and store in Redis."""
    for view in ("pricing", None):
        key_suffix = view or "default"
        key = f"{_SERVICES_KEY_PREFIX}:{key_suffix}"
        try:
            cards_json = build_pricing_cards_json(db, view)
            redis_client.set(key, cards_json)
        except Exception:
            logger.exception("Failed to rebuild services cache for view=%s", view)


def invalidate_specialists_cache():
    redis_client.delete(_SPECIALISTS_KEY)


def invalidate_locations_cache():
    redis_client.delete(_LOCATIONS_KEY)
