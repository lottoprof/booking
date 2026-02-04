# backend/app/routers/integrations.py
# API endpoints for specialist integrations (Google Calendar)

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import (
    SpecialistIntegrations,
    BookingExternalEvents,
    Specialists,
    Bookings,
    Services,
    Users,
    Locations,
)
from ..schemas.integrations import (
    IntegrationStatusRead,
    IntegrationRead,
    IntegrationUpdate,
    OAuthCallbackResponse,
    BookingExternalEventRead,
)
from ..services.google_calendar import (
    get_oauth_url,
    exchange_code_for_tokens,
    refresh_access_token,
    create_event,
    update_event,
    delete_event,
)
from ..services.events import emit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/google/auth-url")
def get_google_auth_url(
    specialist_id: int = Query(..., description="Specialist ID requesting OAuth"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Generate OAuth URL for Google Calendar authorization.

    The specialist should be redirected to this URL to authorize access.
    """
    # Verify specialist exists
    specialist = db.get(Specialists, specialist_id)
    if not specialist:
        raise HTTPException(status_code=404, detail="Specialist not found")

    url = get_oauth_url(specialist_id)
    return {"auth_url": url}


@router.get("/google/callback", response_model=OAuthCallbackResponse)
def handle_google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter with encoded specialist_id"),
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback from Google.

    Exchanges the authorization code for tokens and saves integration.
    """
    try:
        tokens = exchange_code_for_tokens(code, state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    specialist_id = tokens["specialist_id"]

    # Verify specialist exists
    specialist = db.get(Specialists, specialist_id)
    if not specialist:
        raise HTTPException(status_code=404, detail="Specialist not found")

    # Check if integration already exists
    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id == specialist_id,
        SpecialistIntegrations.provider == "google_calendar",
    ).first()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    if integration:
        # Update existing integration
        integration.access_token = tokens["access_token"]
        integration.refresh_token = tokens["refresh_token"]
        integration.token_expires_at = tokens["token_expires_at"]
        integration.sync_enabled = 1
        integration.updated_at = now
    else:
        # Create new integration
        integration = SpecialistIntegrations(
            specialist_id=specialist_id,
            provider="google_calendar",
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            token_expires_at=tokens["token_expires_at"],
            calendar_id="primary",
            sync_enabled=1,
            created_at=now,
            updated_at=now,
        )
        db.add(integration)

    db.commit()

    # Emit event for bot notification
    emit_event("google_calendar_connected", {
        "specialist_id": specialist_id,
        "user_id": specialist.user_id,
    })

    logger.info(f"Google Calendar connected for specialist {specialist_id}")

    return OAuthCallbackResponse(
        success=True,
        specialist_id=specialist_id,
        message="Google Calendar connected successfully",
    )


@router.get("/specialist/{specialist_id}/status", response_model=IntegrationStatusRead)
def get_integration_status(
    specialist_id: int,
    db: Session = Depends(get_db),
):
    """
    Get integration status for a specialist.

    Returns connection status and settings.
    """
    specialist = db.get(Specialists, specialist_id)
    if not specialist:
        raise HTTPException(status_code=404, detail="Specialist not found")

    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id == specialist_id,
        SpecialistIntegrations.provider == "google_calendar",
    ).first()

    if not integration:
        return IntegrationStatusRead(
            specialist_id=specialist_id,
            provider="google_calendar",
            is_connected=False,
            sync_enabled=False,
            calendar_id=None,
            last_sync_at=None,
            created_at=None,
        )

    return IntegrationStatusRead(
        specialist_id=specialist_id,
        provider=integration.provider,
        is_connected=bool(integration.access_token),
        sync_enabled=bool(integration.sync_enabled),
        calendar_id=integration.calendar_id,
        last_sync_at=integration.last_sync_at,
        created_at=integration.created_at,
    )


@router.patch("/specialist/{specialist_id}/google", response_model=IntegrationStatusRead)
def update_integration(
    specialist_id: int,
    data: IntegrationUpdate,
    db: Session = Depends(get_db),
):
    """
    Update integration settings.

    Allows enabling/disabling sync and changing calendar ID.
    """
    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id == specialist_id,
        SpecialistIntegrations.provider == "google_calendar",
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(integration, field, value)

    integration.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    db.commit()
    db.refresh(integration)

    return IntegrationStatusRead(
        specialist_id=specialist_id,
        provider=integration.provider,
        is_connected=bool(integration.access_token),
        sync_enabled=bool(integration.sync_enabled),
        calendar_id=integration.calendar_id,
        last_sync_at=integration.last_sync_at,
        created_at=integration.created_at,
    )


@router.delete("/specialist/{specialist_id}/google", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    specialist_id: int,
    db: Session = Depends(get_db),
):
    """
    Disconnect Google Calendar integration.

    Removes tokens and disables sync.
    """
    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id == specialist_id,
        SpecialistIntegrations.provider == "google_calendar",
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Get specialist for event
    specialist = db.get(Specialists, specialist_id)

    # Delete the integration
    db.delete(integration)
    db.commit()

    # Emit event for bot notification
    if specialist:
        emit_event("google_calendar_disconnected", {
            "specialist_id": specialist_id,
            "user_id": specialist.user_id,
        })

    logger.info(f"Google Calendar disconnected for specialist {specialist_id}")


@router.post("/booking/{booking_id}/sync")
def sync_booking_to_calendar(
    booking_id: int,
    action: str = Query("create", description="Action: create, update, or delete"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Sync a booking to Google Calendar.

    This endpoint is called internally by the bot event handler.

    Actions:
    - create: Create new calendar event
    - update: Update existing event
    - delete: Delete calendar event
    """
    booking = db.get(Bookings, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get specialist integration
    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id == booking.specialist_id,
        SpecialistIntegrations.provider == "google_calendar",
        SpecialistIntegrations.sync_enabled == 1,
    ).first()

    if not integration:
        return {"synced": False, "reason": "No active integration"}

    # Check if tokens need refresh
    if integration.token_expires_at:
        try:
            expires_at = datetime.strptime(integration.token_expires_at, "%Y-%m-%d %H:%M:%S")
            if expires_at <= datetime.utcnow():
                # Refresh tokens
                new_tokens = refresh_access_token(integration.refresh_token)
                integration.access_token = new_tokens["access_token"]
                integration.token_expires_at = new_tokens["token_expires_at"]
                integration.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                db.commit()
        except ValueError as e:
            logger.error(f"Token refresh failed for specialist {booking.specialist_id}: {e}")
            # Disable sync on refresh failure
            integration.sync_enabled = 0
            integration.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()

            emit_event("google_calendar_auth_failed", {
                "specialist_id": booking.specialist_id,
                "user_id": integration.specialist.user_id,
            })
            return {"synced": False, "reason": "Token refresh failed"}

    # Build booking data for calendar
    service = db.get(Services, booking.service_id)
    client = db.get(Users, booking.client_id)
    location = db.get(Locations, booking.location_id)

    booking_data = {
        "date_start": booking.date_start,
        "date_end": booking.date_end,
        "service_name": service.name if service else "Unknown Service",
        "client_name": f"{client.first_name} {client.last_name or ''}".strip() if client else "Unknown Client",
        "client_phone": client.phone if client else None,
        "location_name": location.name if location else None,
        "final_price": booking.final_price,
        "duration_minutes": booking.duration_minutes,
        "notes": booking.notes,
    }

    try:
        if action == "create":
            # Check if event already exists
            existing = db.query(BookingExternalEvents).filter(
                BookingExternalEvents.booking_id == booking_id,
                BookingExternalEvents.specialist_integration_id == integration.id,
            ).first()

            if existing:
                return {"synced": False, "reason": "Event already exists"}

            result = create_event(
                access_token=integration.access_token,
                refresh_token=integration.refresh_token,
                calendar_id=integration.calendar_id or "primary",
                booking=booking_data,
            )

            # Save external event link
            external_event = BookingExternalEvents(
                booking_id=booking_id,
                provider="google_calendar",
                external_event_id=result["event_id"],
                specialist_integration_id=integration.id,
                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            )
            db.add(external_event)

            integration.last_sync_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()

            return {"synced": True, "event_id": result["event_id"], "action": "created"}

        elif action == "update":
            external_event = db.query(BookingExternalEvents).filter(
                BookingExternalEvents.booking_id == booking_id,
                BookingExternalEvents.specialist_integration_id == integration.id,
            ).first()

            if not external_event:
                # Create if doesn't exist
                result = create_event(
                    access_token=integration.access_token,
                    refresh_token=integration.refresh_token,
                    calendar_id=integration.calendar_id or "primary",
                    booking=booking_data,
                )

                external_event = BookingExternalEvents(
                    booking_id=booking_id,
                    provider="google_calendar",
                    external_event_id=result["event_id"],
                    specialist_integration_id=integration.id,
                    created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                )
                db.add(external_event)

                integration.last_sync_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                db.commit()

                return {"synced": True, "event_id": result["event_id"], "action": "created"}

            result = update_event(
                access_token=integration.access_token,
                refresh_token=integration.refresh_token,
                calendar_id=integration.calendar_id or "primary",
                event_id=external_event.external_event_id,
                booking=booking_data,
            )

            integration.last_sync_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()

            return {"synced": True, "event_id": result["event_id"], "action": "updated"}

        elif action == "delete":
            external_event = db.query(BookingExternalEvents).filter(
                BookingExternalEvents.booking_id == booking_id,
                BookingExternalEvents.specialist_integration_id == integration.id,
            ).first()

            if not external_event:
                return {"synced": False, "reason": "No external event to delete"}

            delete_event(
                access_token=integration.access_token,
                refresh_token=integration.refresh_token,
                calendar_id=integration.calendar_id or "primary",
                event_id=external_event.external_event_id,
            )

            db.delete(external_event)
            integration.last_sync_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()

            return {"synced": True, "action": "deleted"}

        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    except Exception as e:
        logger.error(f"Calendar sync failed for booking {booking_id}: {e}")
        return {"synced": False, "reason": str(e)}
