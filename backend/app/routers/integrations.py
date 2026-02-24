# backend/app/routers/integrations.py
# API endpoints for specialist integrations (Google Calendar)

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import (
    BookingExternalEvents,
    Bookings,
    Locations,
    ServicePackages,
    Services,
    SpecialistIntegrations,
    Specialists,
    Users,
)
from ..schemas.integrations import (
    BookingExternalEventRead,
    IntegrationRead,
    IntegrationStatusRead,
    IntegrationUpdate,
    OAuthCallbackResponse,
)
from ..services.events import emit_event
from ..services.google_calendar import (
    create_event,
    delete_event,
    exchange_code_for_tokens,
    get_oauth_url,
    refresh_access_token,
    update_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/google/auth-url")
def get_google_auth_url(
    specialist_id: Optional[int] = Query(None, description="Specialist ID requesting OAuth"),
    user_id: Optional[int] = Query(None, description="User ID requesting OAuth (for admin/manager)"),
    sync_scope: str = Query("own", description="Sync scope: own, location, all"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Generate OAuth URL for Google Calendar authorization.

    For specialists: pass specialist_id
    For admins/managers: pass user_id and sync_scope
    """
    if specialist_id:
        # Verify specialist exists
        specialist = db.get(Specialists, specialist_id)
        if not specialist:
            raise HTTPException(status_code=404, detail="Specialist not found")
        url = get_oauth_url(specialist_id=specialist_id)
    elif user_id:
        # Verify user exists
        user = db.get(Users, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        url = get_oauth_url(user_id=user_id, sync_scope=sync_scope)
    else:
        raise HTTPException(status_code=400, detail="Either specialist_id or user_id required")

    return {"auth_url": url}


@router.get("/google/callback", response_model=OAuthCallbackResponse)
def handle_google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter with encoded IDs"),
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback from Google.

    Exchanges the authorization code for tokens and saves integration.
    Supports both specialist and admin/manager integrations.
    """
    try:
        tokens = exchange_code_for_tokens(code, state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    specialist_id = tokens.get("specialist_id")
    user_id = tokens.get("user_id")
    sync_scope = tokens.get("sync_scope", "own")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    if specialist_id:
        # Specialist integration
        specialist = db.get(Specialists, specialist_id)
        if not specialist:
            raise HTTPException(status_code=404, detail="Specialist not found")

        integration = db.query(SpecialistIntegrations).filter(
            SpecialistIntegrations.specialist_id == specialist_id,
            SpecialistIntegrations.provider == "google_calendar",
        ).first()

        if integration:
            integration.access_token = tokens["access_token"]
            integration.refresh_token = tokens["refresh_token"]
            integration.token_expires_at = tokens["token_expires_at"]
            integration.sync_enabled = 1
            integration.updated_at = now
        else:
            integration = SpecialistIntegrations(
                specialist_id=specialist_id,
                provider="google_calendar",
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_expires_at=tokens["token_expires_at"],
                calendar_id="primary",
                sync_enabled=1,
                sync_scope="own",
                created_at=now,
                updated_at=now,
            )
            db.add(integration)

        db.commit()

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

    elif user_id:
        # Admin/Manager integration
        user = db.get(Users, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        integration = db.query(SpecialistIntegrations).filter(
            SpecialistIntegrations.user_id == user_id,
            SpecialistIntegrations.specialist_id.is_(None),
            SpecialistIntegrations.provider == "google_calendar",
        ).first()

        if integration:
            integration.access_token = tokens["access_token"]
            integration.refresh_token = tokens["refresh_token"]
            integration.token_expires_at = tokens["token_expires_at"]
            integration.sync_enabled = 1
            integration.sync_scope = sync_scope
            integration.updated_at = now
        else:
            integration = SpecialistIntegrations(
                user_id=user_id,
                specialist_id=None,
                provider="google_calendar",
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_expires_at=tokens["token_expires_at"],
                calendar_id="primary",
                sync_enabled=1,
                sync_scope=sync_scope,
                created_at=now,
                updated_at=now,
            )
            db.add(integration)

        db.commit()

        emit_event("google_calendar_connected", {
            "user_id": user_id,
            "sync_scope": sync_scope,
        })

        logger.info(f"Google Calendar connected for user {user_id} (scope: {sync_scope})")

        return OAuthCallbackResponse(
            success=True,
            specialist_id=0,
            message="Google Calendar connected successfully",
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid state parameter")


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


# ============================================================
# Admin/Manager Integration Endpoints
# ============================================================

@router.get("/user/{user_id}/status", response_model=IntegrationStatusRead)
def get_user_integration_status(
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    Get integration status for admin/manager user.

    Returns connection status and settings.
    """
    user = db.get(Users, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.user_id == user_id,
        SpecialistIntegrations.specialist_id.is_(None),
        SpecialistIntegrations.provider == "google_calendar",
    ).first()

    if not integration:
        return IntegrationStatusRead(
            specialist_id=0,
            provider="google_calendar",
            is_connected=False,
            sync_enabled=False,
            sync_scope="all",
            calendar_id=None,
            last_sync_at=None,
            created_at=None,
        )

    return IntegrationStatusRead(
        specialist_id=0,
        provider=integration.provider,
        is_connected=bool(integration.access_token),
        sync_enabled=bool(integration.sync_enabled),
        sync_scope=integration.sync_scope or "all",
        calendar_id=integration.calendar_id,
        last_sync_at=integration.last_sync_at,
        created_at=integration.created_at,
    )


@router.patch("/user/{user_id}/google", response_model=IntegrationStatusRead)
def update_user_integration(
    user_id: int,
    data: IntegrationUpdate,
    db: Session = Depends(get_db),
):
    """
    Update admin/manager integration settings.
    """
    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.user_id == user_id,
        SpecialistIntegrations.specialist_id.is_(None),
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
        specialist_id=0,
        provider=integration.provider,
        is_connected=bool(integration.access_token),
        sync_enabled=bool(integration.sync_enabled),
        sync_scope=integration.sync_scope or "all",
        calendar_id=integration.calendar_id,
        last_sync_at=integration.last_sync_at,
        created_at=integration.created_at,
    )


@router.delete("/user/{user_id}/google", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_user_integration(
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    Disconnect Google Calendar for admin/manager.
    """
    integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.user_id == user_id,
        SpecialistIntegrations.specialist_id.is_(None),
        SpecialistIntegrations.provider == "google_calendar",
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    db.delete(integration)
    db.commit()

    emit_event("google_calendar_disconnected", {
        "user_id": user_id,
    })

    logger.info(f"Google Calendar disconnected for user {user_id}")


def _get_integrations_for_booking(db: Session, booking: Bookings) -> list:
    """
    Get all integrations that should receive this booking.

    Returns list of integrations:
    - Specialist's own integration (sync_scope='own')
    - Admin integrations with sync_scope='all'
    - Manager integrations with sync_scope='location' matching booking's location
    """
    integrations = []

    # 1. Specialist's integration
    spec_integration = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id == booking.specialist_id,
        SpecialistIntegrations.provider == "google_calendar",
        SpecialistIntegrations.sync_enabled == 1,
    ).first()
    if spec_integration:
        integrations.append(spec_integration)

    # 2. Admin integrations (sync_scope='all')
    admin_integrations = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id.is_(None),
        SpecialistIntegrations.user_id.isnot(None),
        SpecialistIntegrations.provider == "google_calendar",
        SpecialistIntegrations.sync_enabled == 1,
        SpecialistIntegrations.sync_scope == "all",
    ).all()
    integrations.extend(admin_integrations)

    # 3. Manager integrations (sync_scope='location' with matching location)
    manager_integrations = db.query(SpecialistIntegrations).filter(
        SpecialistIntegrations.specialist_id.is_(None),
        SpecialistIntegrations.user_id.isnot(None),
        SpecialistIntegrations.provider == "google_calendar",
        SpecialistIntegrations.sync_enabled == 1,
        SpecialistIntegrations.sync_scope == "location",
        SpecialistIntegrations.location_id == booking.location_id,
    ).all()
    integrations.extend(manager_integrations)

    return integrations


def _refresh_integration_token(db: Session, integration: SpecialistIntegrations) -> bool:
    """
    Refresh token for an integration if expired.
    Returns True if token is valid/refreshed, False if refresh failed.
    """
    if not integration.token_expires_at:
        return True

    try:
        expires_at = datetime.strptime(integration.token_expires_at, "%Y-%m-%d %H:%M:%S")
        if expires_at <= datetime.utcnow():
            new_tokens = refresh_access_token(integration.refresh_token)
            integration.access_token = new_tokens["access_token"]
            integration.token_expires_at = new_tokens["token_expires_at"]
            integration.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()
        return True
    except ValueError as e:
        logger.error(f"Token refresh failed for integration {integration.id}: {e}")
        integration.sync_enabled = 0
        integration.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()

        # Emit auth failed event
        user_id = integration.user_id
        if integration.specialist_id and integration.specialist:
            user_id = integration.specialist.user_id
        emit_event("google_calendar_auth_failed", {
            "specialist_id": integration.specialist_id,
            "user_id": user_id,
        })
        return False


def _sync_single_integration(
    db: Session,
    integration: SpecialistIntegrations,
    booking_id: int,
    booking_data: dict,
    action: str,
) -> dict:
    """Sync booking to a single integration. Returns result dict."""
    try:
        if action == "create":
            existing = db.query(BookingExternalEvents).filter(
                BookingExternalEvents.booking_id == booking_id,
                BookingExternalEvents.specialist_integration_id == integration.id,
            ).first()

            if existing:
                return {"integration_id": integration.id, "synced": False, "reason": "Already exists"}

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

            return {"integration_id": integration.id, "synced": True, "event_id": result["event_id"], "action": "created"}

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

                return {"integration_id": integration.id, "synced": True, "event_id": result["event_id"], "action": "created"}

            result = update_event(
                access_token=integration.access_token,
                refresh_token=integration.refresh_token,
                calendar_id=integration.calendar_id or "primary",
                event_id=external_event.external_event_id,
                booking=booking_data,
            )
            integration.last_sync_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            return {"integration_id": integration.id, "synced": True, "event_id": result["event_id"], "action": "updated"}

        elif action == "delete":
            external_event = db.query(BookingExternalEvents).filter(
                BookingExternalEvents.booking_id == booking_id,
                BookingExternalEvents.specialist_integration_id == integration.id,
            ).first()

            if not external_event:
                return {"integration_id": integration.id, "synced": False, "reason": "No event to delete"}

            delete_event(
                access_token=integration.access_token,
                refresh_token=integration.refresh_token,
                calendar_id=integration.calendar_id or "primary",
                event_id=external_event.external_event_id,
            )

            db.delete(external_event)
            integration.last_sync_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            return {"integration_id": integration.id, "synced": True, "action": "deleted"}

        else:
            return {"integration_id": integration.id, "synced": False, "reason": f"Invalid action: {action}"}

    except Exception as e:
        logger.error(f"Sync failed for integration {integration.id}: {e}")
        return {"integration_id": integration.id, "synced": False, "reason": str(e)}


@router.post("/booking/{booking_id}/sync")
def sync_booking_to_calendar(
    booking_id: int,
    action: str = Query("create", description="Action: create, update, or delete"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Sync a booking to Google Calendar.

    This endpoint is called internally by the bot event handler.
    Syncs to all applicable integrations:
    - Specialist's calendar (if connected)
    - Admin calendars with sync_scope='all'
    - Manager calendars with sync_scope='location' matching booking location

    Actions:
    - create: Create new calendar event
    - update: Update existing event
    - delete: Delete calendar event
    """
    booking = db.get(Bookings, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get all integrations for this booking
    integrations = _get_integrations_for_booking(db, booking)

    if not integrations:
        return {"synced": False, "reason": "No active integrations", "results": []}

    # Build booking data for calendar
    # Use package name if available, fallback to service name
    service_name = "Unknown Service"
    color_code = None
    if booking.service_package_id:
        package = db.get(ServicePackages, booking.service_package_id)
        if package:
            service_name = package.name
    if service_name == "Unknown Service" and booking.service_id:
        service = db.get(Services, booking.service_id)
        if service:
            service_name = service.name
            color_code = service.color_code

    client = db.get(Users, booking.client_id)
    location = db.get(Locations, booking.location_id)
    specialist = db.get(Specialists, booking.specialist_id)
    specialist_user = db.get(Users, specialist.user_id) if specialist else None

    booking_data = {
        "date_start": booking.date_start,
        "date_end": booking.date_end,
        "service_name": service_name,
        "color_code": color_code,
        "client_name": client.first_name if client else "Unknown Client",
        "client_phone": client.phone if client else None,
        "location_name": location.name if location else None,
        "specialist_name": specialist_user.first_name if specialist_user else None,
        "final_price": booking.final_price,
        "duration_minutes": booking.duration_minutes,
        "notes": booking.notes,
    }

    results = []
    any_synced = False

    for integration in integrations:
        # Refresh token if needed
        if not _refresh_integration_token(db, integration):
            results.append({"integration_id": integration.id, "synced": False, "reason": "Token refresh failed"})
            continue

        result = _sync_single_integration(db, integration, booking_id, booking_data, action)
        results.append(result)
        if result.get("synced"):
            any_synced = True

    db.commit()

    return {
        "synced": any_synced,
        "total_integrations": len(integrations),
        "results": results,
    }
