"""Invalidate gateway web cache keys after admin CRUD."""
from ..redis_client import redis_client

_SERVICES_KEYS = ("cache:web:services", "cache:web:services:pricing", "cache:web:services:default")
_SPECIALISTS_KEY = "cache:web:specialists"
_LOCATIONS_KEY = "cache:web:locations"


def invalidate_services_cache():
    redis_client.delete(*_SERVICES_KEYS)


def invalidate_specialists_cache():
    redis_client.delete(_SPECIALISTS_KEY)


def invalidate_locations_cache():
    redis_client.delete(_LOCATIONS_KEY)
