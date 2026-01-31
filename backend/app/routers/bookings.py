# backend/app/routers/bookings.py
# API.md: Extended with filters and PATCH support for admin module

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models.generated import Bookings as DBBookings
from ..schemas.bookings import (
    BookingCreate,
    BookingUpdate,
    BookingRead,
)
from ..services.events import emit_event
from ..services.booking_payment import process_booking_payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/", response_model=list[BookingRead])
def list_bookings(
    client_id: Optional[int] = Query(None, description="Filter by client"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    specialist_id: Optional[int] = Query(None, description="Filter by specialist"),
    status: Optional[str] = Query(None, description="Filter by status"),
    date: Optional[str] = Query(None, description="Filter by exact date (YYYY-MM-DD)"),
    date_from: Optional[str] = Query(None, description="Filter date_start >= date_from"),
    date_to: Optional[str] = Query(None, description="Filter date_start <= date_to"),
    db: Session = Depends(get_db),
):
    """
    List bookings with optional filters.
    
    Filters:
    - client_id: Filter by client user ID
    - location_id: Filter by location ID
    - specialist_id: Filter by specialist ID
    - status: Filter by booking status (pending, confirmed, cancelled, done)
    - date: Filter by exact date (date_start starts on this date)
    - date_from: Filter bookings with date_start >= date_from
    - date_to: Filter bookings with date_start <= date_to
    
    Returns bookings ordered by date_start ASC.
    """
    query = db.query(DBBookings)
    
    # Apply filters
    if client_id is not None:
        query = query.filter(DBBookings.client_id == client_id)
    
    if location_id is not None:
        query = query.filter(DBBookings.location_id == location_id)
    
    if specialist_id is not None:
        query = query.filter(DBBookings.specialist_id == specialist_id)
    
    if status is not None:
        query = query.filter(DBBookings.status == status)
    
    # Date filters using SQLite date() function
    # date_start is stored as TEXT in ISO format
    if date is not None:
        # Exact date match: DATE(date_start) = date
        query = query.filter(
            func.date(DBBookings.date_start) == date
        )
    
    if date_from is not None:
        # date_start >= date_from
        query = query.filter(
            func.date(DBBookings.date_start) >= date_from
        )
    
    if date_to is not None:
        # date_start <= date_to
        query = query.filter(
            func.date(DBBookings.date_start) <= date_to
        )
    
    # Order by date_start ascending
    query = query.order_by(DBBookings.date_start.asc())
    
    return query.all()


@router.get("/{id}", response_model=BookingRead)
def get_booking(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBBookings, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(
    data: BookingCreate,
    db: Session = Depends(get_db),
    x_initiated_by_user_id: Optional[int] = Header(None),
    x_initiated_by_role: Optional[str] = Header(None),
    x_initiated_by_channel: Optional[str] = Header(None),
):
    obj = DBBookings(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)

    # Emit booking_created event
    initiated_by = None
    if x_initiated_by_user_id:
        initiated_by = {
            "user_id": x_initiated_by_user_id,
            "role": x_initiated_by_role or "unknown",
            "channel": x_initiated_by_channel or "api",
        }

    emit_event("booking_created", {
        "booking_id": obj.id,
        "initiated_by": initiated_by,
    })

    return obj


@router.patch("/{id}", response_model=BookingRead)
def update_booking(
    id: int,
    data: BookingUpdate,
    db: Session = Depends(get_db),
    x_initiated_by_user_id: Optional[int] = Header(None),
    x_initiated_by_role: Optional[str] = Header(None),
    x_initiated_by_channel: Optional[str] = Header(None),
):
    """
    Update booking fields.

    Supports updating:
    - date_start, date_end: Reschedule appointment
    - specialist_id: Change specialist
    - service_id: Change service
    - duration_minutes: Update duration
    - final_price: Update price
    - room_id: Change room
    - status: Change booking status
    - cancel_reason: Add cancellation reason
    - notes: Update notes

    Note: updated_at is automatically set to current timestamp.
    """
    obj = db.get(DBBookings, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    changes = data.model_dump(exclude_unset=True)

    # Capture old values for event emission
    old_date_start = obj.date_start
    old_status = obj.status

    for field, value in changes.items():
        setattr(obj, field, value)

    # Update timestamp
    obj.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    db.commit()
    db.refresh(obj)

    # Emit events based on what changed
    initiated_by = None
    if x_initiated_by_user_id:
        initiated_by = {
            "user_id": x_initiated_by_user_id,
            "role": x_initiated_by_role or "unknown",
            "channel": x_initiated_by_channel or "api",
        }

    new_status = changes.get("status")
    new_date_start = changes.get("date_start")

    if new_status == "cancelled" and old_status != "cancelled":
        emit_event("booking_cancelled", {
            "booking_id": obj.id,
            "initiated_by": initiated_by,
        })
    elif new_date_start and str(new_date_start) != str(old_date_start):
        emit_event("booking_rescheduled", {
            "booking_id": obj.id,
            "old_datetime": str(old_date_start),
            "new_datetime": str(new_date_start),
            "initiated_by": initiated_by,
        })

    # Process payment when status changes to done
    if new_status == "done" and old_status != "done":
        try:
            payment_result = process_booking_payment(
                db=db,
                booking_id=obj.id,
                created_by=x_initiated_by_user_id,
            )
            db.commit()
            db.refresh(obj)
            logger.info(
                f"Booking {obj.id} payment processed: "
                f"source={payment_result['source']}, "
                f"amount={payment_result['amount']}"
            )
        except Exception as e:
            logger.exception(f"Failed to process payment for booking {obj.id}: {e}")
            # Don't fail the status update, just log the error

    return obj


@router.delete("/{id}")
def delete_not_allowed():
    """
    DELETE is not allowed for bookings.
    Use PATCH to change status to 'cancelled' instead.
    """
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed. Use PATCH to cancel booking.",
    )

