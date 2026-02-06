# gateway/app/events/__init__.py

from .web_booking_consumer import web_booking_consumer_loop

__all__ = ["web_booking_consumer_loop"]
