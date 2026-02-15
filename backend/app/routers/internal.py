# backend/app/routers/internal.py
"""
Internal API endpoints for trusted consumers.

These endpoints are NOT exposed through the Gateway proxy.
They are called directly by trusted services (e.g., web_booking_consumer).

Access: localhost only (validated by Gateway not proxying /internal/*)
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from ..models.generated import (
    Users as DBUsers,
    Bookings as DBBookings,
    Services as DBServices,
    ServicePackages as DBServicePackages,
    Locations as DBLocations,
    Specialists as DBSpecialists,
    UserRoles as DBUserRoles,
)
from ..services.events import emit_event
from ..services.slots.availability import calculate_service_availability
from ..services.slots.config import get_booking_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

# Client role ID
CLIENT_ROLE_ID = 4


# ──────────────────────────────────────────────────────────────────────────────
# Request/Response schemas
# ──────────────────────────────────────────────────────────────────────────────

class WebBookingCreate(BaseModel):
    """Request body for creating booking from web."""
    location_id: int
    service_id: Optional[int] = None
    service_package_id: Optional[int] = None
    specialist_id: Optional[int] = None
    date: str = Field(description="Date in YYYY-MM-DD format")
    time: str = Field(description="Time in HH:MM format")
    phone: str = Field(description="Client phone number")
    name: Optional[str] = Field(None, description="Client name")

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        """Normalize phone to E.164-like format."""
        # Remove all non-digit characters except leading +
        if v.startswith("+"):
            return "+" + re.sub(r"\D", "", v[1:])
        digits = re.sub(r"\D", "", v)
        # Assume Russian phone if starts with 7 or 8
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        if not digits.startswith("7") and len(digits) == 10:
            digits = "7" + digits
        return "+" + digits

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        """Validate time format."""
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Time must be in HH:MM format")
        return v


class WebBookingResponse(BaseModel):
    """Response after creating booking from web."""
    booking_id: int
    client_id: int
    status: str = "pending"


# ──────────────────────────────────────────────────────────────────────────────
# Internal endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/bookings/from-web", response_model=WebBookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking_from_web(
    data: WebBookingCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a booking from web form.

    This is a trusted endpoint called by the web_booking_consumer.

    Steps:
    1. Validate location and service exist
    2. Find or create user by phone
    3. Validate slot is available
    4. Select specialist (if not provided, pick first available)
    5. Create booking

    Returns:
        booking_id, client_id, status
    """
    # Security: Only allow requests from localhost
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "localhost", "::1", None):
        logger.warning(f"Internal endpoint called from non-localhost: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal endpoints are only accessible from localhost"
        )

    # Step 1: Validate location
    location = db.get(DBLocations, data.location_id)
    if not location or not location.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Location not found or inactive"
        )

    # Step 2: Resolve service_id from service_package if needed
    service_package_id = data.service_package_id
    service_id = data.service_id

    if not service_id and service_package_id:
        package = db.get(DBServicePackages, service_package_id)
        if not package or not package.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service package not found or inactive"
            )
        try:
            items = json.loads(package.package_items) if package.package_items else []
        except (json.JSONDecodeError, TypeError):
            items = []
        if not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service package has no items"
            )
        service_id = items[0].get("service_id")

    if not service_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either service_id or service_package_id is required"
        )

    service = db.get(DBServices, service_id)
    if not service or not service.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service not found or inactive"
        )

    # Step 3: Find or create user by phone
    client = _find_or_create_user(db, data.phone, data.name, location.company_id)

    # Step 4: Validate slot availability and select specialist
    specialist_id = data.specialist_id
    if not specialist_id:
        # Find first available specialist
        specialist_id = _find_available_specialist(
            db, data.location_id, service_id, data.date, data.time
        )
        if not specialist_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No specialists available for this time slot"
            )
    else:
        # Validate specified specialist is available
        if not _is_specialist_available(
            db, specialist_id, service_id, data.date, data.time
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected specialist is not available for this time slot"
            )

    # Validate specialist exists
    specialist = db.get(DBSpecialists, specialist_id)
    if not specialist or not specialist.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Specialist not found or inactive"
        )

    # Step 5: Create booking
    duration_min = service.duration_min
    break_min = service.break_min or 0

    # Parse date and time
    date_start_str = f"{data.date} {data.time}:00"
    date_start = datetime.strptime(date_start_str, "%Y-%m-%d %H:%M:%S")
    date_end = date_start + timedelta(minutes=duration_min)

    booking = DBBookings(
        company_id=location.company_id,
        location_id=data.location_id,
        service_id=service_id,
        service_package_id=service_package_id,
        client_id=client.id,
        specialist_id=specialist_id,
        date_start=date_start.strftime("%Y-%m-%d %H:%M:%S"),
        date_end=date_end.strftime("%Y-%m-%d %H:%M:%S"),
        duration_minutes=duration_min,
        break_minutes=break_min,
        status="pending",
        notes=f"Web booking | Phone: {data.phone}",
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    logger.info(
        f"Web booking created: booking_id={booking.id}, "
        f"client_id={client.id}, service={service.name}, "
        f"specialist_id={specialist_id}, time={data.date} {data.time}"
    )

    # Emit booking_created event
    emit_event("booking_created", {
        "booking_id": booking.id,
        "initiated_by": {
            "user_id": client.id,
            "role": "client",
            "channel": "web",
        }
    })

    return WebBookingResponse(
        booking_id=booking.id,
        client_id=client.id,
        status="pending"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _find_or_create_user(
    db: Session,
    phone: str,
    name: Optional[str],
    company_id: int,
) -> DBUsers:
    """Find user by phone or create new one."""
    # Try to find existing user
    user = db.query(DBUsers).filter(DBUsers.phone == phone).first()

    if user:
        # Update name if provided and user has no name
        if name and not user.first_name:
            user.first_name = name
            db.commit()
            db.refresh(user)
        return user

    # Create new user
    first_name = name or "Web Client"
    user = DBUsers(
        company_id=company_id,
        phone=phone,
        first_name=first_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Add client role
    user_role = DBUserRoles(
        user_id=user.id,
        role_id=CLIENT_ROLE_ID,
    )
    db.add(user_role)
    db.commit()

    logger.info(f"Created new user from web: user_id={user.id}, phone={phone}")

    return user


def _find_available_specialist(
    db: Session,
    location_id: int,
    service_id: int,
    date_str: str,
    time_str: str,
) -> Optional[int]:
    """Find first available specialist for the time slot."""
    from datetime import date as date_type

    target_date = date_type.fromisoformat(date_str)
    config = get_booking_config()

    availability = calculate_service_availability(
        db=db,
        location_id=location_id,
        service_id=service_id,
        target_date=target_date,
        config=config,
    )

    for slot in availability.get("available_times", []):
        if slot["time"] == time_str:
            specialists = slot.get("specialists", [])
            if specialists:
                return specialists[0]["id"]

    return None


def _is_specialist_available(
    db: Session,
    specialist_id: int,
    service_id: int,
    date_str: str,
    time_str: str,
) -> bool:
    """Check if a specific specialist is available for the time slot."""
    # Get specialist's location
    specialist = db.get(DBSpecialists, specialist_id)
    if not specialist:
        return False

    # Get location from specialist's bookings or first location
    result = db.execute(
        text("""
            SELECT DISTINCT location_id
            FROM bookings
            WHERE specialist_id = :spec_id
            LIMIT 1
        """),
        {"spec_id": specialist_id}
    ).fetchone()

    if result:
        location_id = result[0]
    else:
        # Fallback: get first active location
        location = db.query(DBLocations).filter(DBLocations.is_active == 1).first()
        if not location:
            return False
        location_id = location.id

    from datetime import date as date_type
    target_date = date_type.fromisoformat(date_str)
    config = get_booking_config()

    availability = calculate_service_availability(
        db=db,
        location_id=location_id,
        service_id=service_id,
        target_date=target_date,
        config=config,
    )

    for slot in availability.get("available_times", []):
        if slot["time"] == time_str:
            for spec in slot.get("specialists", []):
                if spec["id"] == specialist_id:
                    return True

    return False
