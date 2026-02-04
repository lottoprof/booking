"""
backend/app/services/google_calendar.py

Google Calendar integration service for specialists.

Handles:
- OAuth URL generation and token exchange
- Access token refresh
- Calendar event CRUD operations
"""

import json
import logging
import os
import secrets
from datetime import datetime
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# OAuth configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

# Scopes needed for calendar access
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# State encryption key (in production, use proper encryption)
STATE_SECRET = os.getenv("GOOGLE_STATE_SECRET", "default-state-secret-key")


def _get_client_config() -> dict:
    """Build OAuth client configuration from environment variables."""
    return {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }


def _encode_state(
    specialist_id: int = None,
    user_id: int = None,
    sync_scope: str = "own"
) -> str:
    """Encode IDs into OAuth state parameter.

    Format: s:{specialist_id}:u:{user_id}:sc:{sync_scope}:{nonce}
    """
    nonce = secrets.token_hex(8)
    parts = []
    if specialist_id:
        parts.append(f"s:{specialist_id}")
    if user_id:
        parts.append(f"u:{user_id}")
    parts.append(f"sc:{sync_scope}")
    parts.append(nonce)
    return ":".join(parts)


def _decode_state(state: str) -> dict:
    """Decode state parameter into dict with specialist_id, user_id, sync_scope."""
    result = {"specialist_id": None, "user_id": None, "sync_scope": "own"}
    try:
        parts = state.split(":")
        i = 0
        while i < len(parts):
            if parts[i] == "s" and i + 1 < len(parts):
                result["specialist_id"] = int(parts[i + 1])
                i += 2
            elif parts[i] == "u" and i + 1 < len(parts):
                result["user_id"] = int(parts[i + 1])
                i += 2
            elif parts[i] == "sc" and i + 1 < len(parts):
                result["sync_scope"] = parts[i + 1]
                i += 2
            else:
                i += 1
    except (ValueError, AttributeError, IndexError):
        pass
    return result


def get_oauth_url(
    specialist_id: int = None,
    user_id: int = None,
    sync_scope: str = "own"
) -> str:
    """
    Generate OAuth URL for Google Calendar authorization.

    Args:
        specialist_id: ID of the specialist requesting authorization
        user_id: ID of the user (admin/manager) requesting authorization
        sync_scope: Scope for sync - 'own', 'location', or 'all'

    Returns:
        Authorization URL to redirect the user to
    """
    flow = Flow.from_client_config(
        _get_client_config(),
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    state = _encode_state(specialist_id=specialist_id, user_id=user_id, sync_scope=sync_scope)

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )

    return authorization_url


def exchange_code_for_tokens(code: str, state: str) -> dict:
    """
    Exchange authorization code for access and refresh tokens.

    Args:
        code: Authorization code from Google OAuth callback
        state: State parameter containing encoded IDs

    Returns:
        Dictionary with tokens and IDs:
        {
            "specialist_id": int or None,
            "user_id": int or None,
            "sync_scope": str,
            "access_token": str,
            "refresh_token": str,
            "token_expires_at": str,
        }

    Raises:
        ValueError: If state is invalid or token exchange fails
    """
    state_data = _decode_state(state)
    if not state_data.get("specialist_id") and not state_data.get("user_id"):
        raise ValueError("Invalid state parameter")

    flow = Flow.from_client_config(
        _get_client_config(),
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Calculate expiry timestamp
        expires_at = None
        if credentials.expiry:
            expires_at = credentials.expiry.strftime("%Y-%m-%d %H:%M:%S")

        return {
            "specialist_id": state_data.get("specialist_id"),
            "user_id": state_data.get("user_id"),
            "sync_scope": state_data.get("sync_scope", "own"),
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_expires_at": expires_at,
        }
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise ValueError(f"Token exchange failed: {e}")


def refresh_access_token(
    refresh_token: str,
) -> dict:
    """
    Refresh an expired access token.

    Args:
        refresh_token: The refresh token from initial authorization

    Returns:
        Dictionary with new tokens:
        {
            "access_token": str,
            "token_expires_at": str,
        }

    Raises:
        ValueError: If refresh fails (token revoked or invalid)
    """
    from google.auth.transport.requests import Request

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )

    try:
        credentials.refresh(Request())

        expires_at = None
        if credentials.expiry:
            expires_at = credentials.expiry.strftime("%Y-%m-%d %H:%M:%S")

        return {
            "access_token": credentials.token,
            "token_expires_at": expires_at,
        }
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise ValueError(f"Token refresh failed: {e}")


def _get_calendar_service(access_token: str, refresh_token: str):
    """Build Google Calendar API service client."""
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )
    return build("calendar", "v3", credentials=credentials)


def create_event(
    access_token: str,
    refresh_token: str,
    calendar_id: str,
    booking: dict,
) -> dict:
    """
    Create a calendar event for a booking.

    Args:
        access_token: Google OAuth access token
        refresh_token: Google OAuth refresh token
        calendar_id: Google Calendar ID (usually 'primary')
        booking: Booking data dictionary with keys:
            - date_start: datetime or ISO string
            - date_end: datetime or ISO string
            - service_name: str
            - client_name: str
            - client_phone: str (optional)
            - location_name: str (optional)
            - final_price: float (optional)
            - notes: str (optional)

    Returns:
        Dictionary with created event info:
        {
            "event_id": str,
            "html_link": str,
        }

    Raises:
        HttpError: If API call fails
    """
    service = _get_calendar_service(access_token, refresh_token)

    # Build event title
    title = f"{booking.get('service_name', 'Booking')} — {booking.get('client_name', 'Client')}"

    # Build description
    description_parts = []
    if booking.get("client_phone"):
        description_parts.append(f"\U0001F4F1 {booking['client_phone']}")
    if booking.get("service_name"):
        duration = booking.get("duration_minutes", 0)
        description_parts.append(f"\U0001F6CE {booking['service_name']} ({duration} min)")
    if booking.get("final_price"):
        description_parts.append(f"\U0001F4B0 {booking['final_price']} \u20BD")
    if booking.get("location_name"):
        description_parts.append(f"\U0001F4CD Location: {booking['location_name']}")
    if booking.get("notes"):
        description_parts.append(f"\U0001F4DD {booking['notes']}")

    description = "\n".join(description_parts)

    # Parse dates
    date_start = booking.get("date_start")
    date_end = booking.get("date_end")

    if isinstance(date_start, str):
        date_start = datetime.fromisoformat(date_start.replace(" ", "T"))
    if isinstance(date_end, str):
        date_end = datetime.fromisoformat(date_end.replace(" ", "T"))

    event = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": date_start.isoformat(),
            "timeZone": "Europe/Moscow",
        },
        "end": {
            "dateTime": date_end.isoformat(),
            "timeZone": "Europe/Moscow",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
            ],
        },
    }

    try:
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event,
        ).execute()

        logger.info(f"Created Google Calendar event: {created_event.get('id')}")

        return {
            "event_id": created_event.get("id"),
            "html_link": created_event.get("htmlLink"),
        }
    except HttpError as e:
        logger.error(f"Failed to create calendar event: {e}")
        raise


def update_event(
    access_token: str,
    refresh_token: str,
    calendar_id: str,
    event_id: str,
    booking: dict,
) -> dict:
    """
    Update an existing calendar event.

    Args:
        access_token: Google OAuth access token
        refresh_token: Google OAuth refresh token
        calendar_id: Google Calendar ID
        event_id: ID of the event to update
        booking: Updated booking data (same format as create_event)

    Returns:
        Dictionary with updated event info

    Raises:
        HttpError: If API call fails
    """
    service = _get_calendar_service(access_token, refresh_token)

    # Build event title
    title = f"{booking.get('service_name', 'Booking')} — {booking.get('client_name', 'Client')}"

    # Build description
    description_parts = []
    if booking.get("client_phone"):
        description_parts.append(f"\U0001F4F1 {booking['client_phone']}")
    if booking.get("service_name"):
        duration = booking.get("duration_minutes", 0)
        description_parts.append(f"\U0001F6CE {booking['service_name']} ({duration} min)")
    if booking.get("final_price"):
        description_parts.append(f"\U0001F4B0 {booking['final_price']} \u20BD")
    if booking.get("location_name"):
        description_parts.append(f"\U0001F4CD Location: {booking['location_name']}")
    if booking.get("notes"):
        description_parts.append(f"\U0001F4DD {booking['notes']}")

    description = "\n".join(description_parts)

    # Parse dates
    date_start = booking.get("date_start")
    date_end = booking.get("date_end")

    if isinstance(date_start, str):
        date_start = datetime.fromisoformat(date_start.replace(" ", "T"))
    if isinstance(date_end, str):
        date_end = datetime.fromisoformat(date_end.replace(" ", "T"))

    event = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": date_start.isoformat(),
            "timeZone": "Europe/Moscow",
        },
        "end": {
            "dateTime": date_end.isoformat(),
            "timeZone": "Europe/Moscow",
        },
    }

    try:
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
        ).execute()

        logger.info(f"Updated Google Calendar event: {event_id}")

        return {
            "event_id": updated_event.get("id"),
            "html_link": updated_event.get("htmlLink"),
        }
    except HttpError as e:
        logger.error(f"Failed to update calendar event: {e}")
        raise


def delete_event(
    access_token: str,
    refresh_token: str,
    calendar_id: str,
    event_id: str,
) -> bool:
    """
    Delete a calendar event.

    Args:
        access_token: Google OAuth access token
        refresh_token: Google OAuth refresh token
        calendar_id: Google Calendar ID
        event_id: ID of the event to delete

    Returns:
        True if deletion was successful

    Raises:
        HttpError: If API call fails
    """
    service = _get_calendar_service(access_token, refresh_token)

    try:
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()

        logger.info(f"Deleted Google Calendar event: {event_id}")
        return True
    except HttpError as e:
        if e.resp.status == 404:
            # Event already deleted
            logger.warning(f"Calendar event not found: {event_id}")
            return True
        logger.error(f"Failed to delete calendar event: {e}")
        raise
