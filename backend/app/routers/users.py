# backend/app/routers/users.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, func, or_
from urllib.parse import unquote

from ..database import get_db
from ..models.generated import Users as DBUsers, Bookings as DBBookings, UserRoles as DBUserRoles
from ..schemas.users import (
    UserCreate,
    UserUpdate,
    UserRead,
    UserStatsRead,
    RoleChangeRequest,
    RoleChangeResponse,
)
from ..schemas.bookings import BookingRead
from ..schemas.bookings import BookingRead, BookingReadWithDetails


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

# Role ID mapping (from schema)
ROLE_IDS = {
    "admin": 1,
    "manager": 2,
    "specialist": 3,
    "client": 4,
}
ROLE_NAMES = {v: k for k, v in ROLE_IDS.items()}


def _merge_web_user_into(db: Session, *, source: DBUsers, target: DBUsers):
    """Merge a web-created user (no tg_id) into a TG user. Deactivate source."""
    sid, tid = source.id, target.id
    for stmt in [
        "UPDATE bookings SET client_id = :tid WHERE client_id = :sid",
        "UPDATE client_packages SET user_id = :tid WHERE user_id = :sid",
        "UPDATE client_wallets SET user_id = :tid WHERE user_id = :sid",
        "UPDATE client_discounts SET user_id = :tid WHERE user_id = :sid",
        "UPDATE wallet_transactions SET created_by = :tid WHERE created_by = :sid",
        "DELETE FROM user_roles WHERE user_id = :sid",
        "UPDATE users SET is_active = 0 WHERE id = :sid",
    ]:
        db.execute(text(stmt), {"sid": sid, "tid": tid})
    logger.info(f"[MERGE] web user {sid} → tg user {tid}")


# ---------------------------------------------------------------------
# Search endpoint (MUST be before /{id} to avoid route conflict)
# ---------------------------------------------------------------------

@router.get("/search", response_model=list[UserRead])
def search_users(
    q: str = Query(..., min_length=2, description="Search query (min 2 chars)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
):
    """
    Search users by phone, first_name, or last_name.

    Returns only active users, ordered by last_name, first_name.

    Note: SQLite's lower() doesn't handle Cyrillic, so we search
    with multiple case variants (original, lowercase, title case).
    """
    # Generate case variants for Cyrillic support
    q_variants = {q, q.lower(), q.title(), q.capitalize()}

    # Build OR conditions for each variant
    filter_conditions = []
    for variant in q_variants:
        pattern = f"%{variant}%"
        filter_conditions.extend([
            DBUsers.phone.like(pattern),
            DBUsers.first_name.like(pattern),
            DBUsers.last_name.like(pattern),
        ])

    results = (
        db.query(DBUsers)
        .filter(DBUsers.is_active == 1)
        .filter(or_(*filter_conditions))
        .order_by(DBUsers.last_name, DBUsers.first_name)
        .limit(limit)
        .all()
    )

    return results


# ---------------------------------------------------------------------
# Base CRUD
# ---------------------------------------------------------------------

@router.get("/", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return (
        db.query(DBUsers)
        .filter(DBUsers.is_active == 1)
        .all()
    )


@router.get("/by_tg/{tg_id}", response_model=UserRead)
def get_user_by_tg_id(tg_id: int, db: Session = Depends(get_db)):
    obj = (
        db.query(DBUsers)
        .filter(DBUsers.tg_id == tg_id, DBUsers.is_active == 1)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    return obj


@router.get("/by_phone/{phone}", response_model=UserRead)
def get_user_by_phone(phone: str, db: Session = Depends(get_db)):
    """
    Search user by phone.
    Returns user regardless of is_active (for deactivation check).
    """
    phone = unquote(phone)
    
    obj = (
        db.query(DBUsers)
        .filter(DBUsers.phone == phone)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    return obj


# ---------------------------------------------------------------------
# User stats endpoint
# ---------------------------------------------------------------------

@router.get("/{id}/stats", response_model=UserStatsRead)
def get_user_stats(id: int, db: Session = Depends(get_db)):
    """
    Get booking statistics for a user.
    
    Returns counts of total, active, completed, and cancelled bookings.
    """
    # Verify user exists
    user = db.get(DBUsers, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Aggregate booking stats
    stats = db.execute(
        text("""
            SELECT 
                COUNT(*) as total_bookings,
                SUM(CASE WHEN status IN ('pending', 'confirmed') THEN 1 ELSE 0 END) as active_bookings,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as completed_bookings,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_bookings
            FROM bookings
            WHERE client_id = :user_id
        """),
        {"user_id": id}
    ).fetchone()
    
    return UserStatsRead(
        user_id=id,
        total_bookings=stats[0] or 0,
        active_bookings=stats[1] or 0,
        completed_bookings=stats[2] or 0,
        cancelled_bookings=stats[3] or 0,
    )



# ---------------------------------------------------------------------
# Active bookings endpoint
# ---------------------------------------------------------------------

@router.get("/{id}/active-bookings", response_model=list[BookingReadWithDetails])
def get_user_active_bookings(id: int, db: Session = Depends(get_db)):
    """
    Get active bookings for a user (status: pending or confirmed).
    
    Returns bookings with service_name, specialist_name, location_name.
    """
    # Verify user exists
    user = db.get(DBUsers, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    bookings = (
        db.query(DBBookings)
        .options(
            joinedload(DBBookings.service),
            joinedload(DBBookings.specialist),
            joinedload(DBBookings.location),
        )
        .filter(
            DBBookings.client_id == id,
            DBBookings.status.in_(["pending", "confirmed"])
        )
        .order_by(DBBookings.date_start)
        .all()
    )
    
    # Map to extended schema
    result = []
    for b in bookings:
        data = BookingReadWithDetails.model_validate(b)
        data.service_name = b.service.name if b.service else None
        data.specialist_name = b.specialist.display_name or (b.specialist.user.first_name if b.specialist and b.specialist.user else None)
        data.location_name = b.location.name if b.location else None
        result.append(data)
    
    return result

# ---------------------------------------------------------------------
# Role change endpoint
# ---------------------------------------------------------------------

@router.patch("/{id}/role", response_model=RoleChangeResponse)
def change_user_role(
    id: int,
    data: RoleChangeRequest,
    db: Session = Depends(get_db),
):
    """
    Change user's primary role.
    
    Updates the user_roles table:
    - client → role_id = 4
    - specialist → role_id = 3
    - manager → role_id = 2
    
    Note: When changing to 'specialist', the specialist record must be
    created separately via POST /specialists/.
    """
    # Verify user exists
    user = db.get(DBUsers, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate new role
    new_role = data.role.lower()
    if new_role not in ROLE_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {list(ROLE_IDS.keys())}"
        )
    
    new_role_id = ROLE_IDS[new_role]
    
    # Find current role (highest priority)
    current_role_record = (
        db.query(DBUserRoles)
        .filter(DBUserRoles.user_id == id)
        .order_by(DBUserRoles.role_id)  # Lower id = higher priority
        .first()
    )
    
    old_role = "client"  # default if no role record
    if current_role_record:
        old_role = ROLE_NAMES.get(current_role_record.role_id, "client")
        # Update existing role
        current_role_record.role_id = new_role_id
    else:
        # Create new role record
        new_role_record = DBUserRoles(user_id=id, role_id=new_role_id)
        db.add(new_role_record)
    
    db.commit()
    
    return RoleChangeResponse(
        user_id=id,
        old_role=old_role,
        new_role=new_role,
    )


# ---------------------------------------------------------------------
# Get user by ID (after specific routes)
# ---------------------------------------------------------------------

@router.get("/{id}", response_model=UserRead)
def get_user(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBUsers, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
):
    obj = DBUsers(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=UserRead)
def update_user(
    id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBUsers, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    update_data = data.model_dump(exclude_unset=True)
    
    # ==========================================================
    # MATCHING: imported_clients → users
    # ==========================================================
    if "phone" in update_data and update_data["phone"]:
        phone = update_data["phone"]
        try:
            result = db.execute(
                text("""
                    SELECT id, first_name, last_name
                    FROM imported_clients
                    WHERE phone = :phone
                      AND matched_user_id IS NULL
                """),
                {"phone": phone}
            ).fetchone()
            
            if result:
                imported_id, imported_first, imported_last = result
                
                if imported_first and "first_name" not in update_data:
                    update_data["first_name"] = imported_first
                if imported_last and "last_name" not in update_data:
                    update_data["last_name"] = imported_last
                
                db.execute(
                    text("""
                        UPDATE imported_clients
                        SET matched_user_id = :user_id,
                            matched_at = :now
                        WHERE id = :id
                    """),
                    {
                        "user_id": id,
                        "now": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        "id": imported_id
                    }
                )
                logger.info(f"[MATCHING] imported_clients.id={imported_id} → users.id={id}")
                
        except Exception as e:
            logger.debug(f"[MATCHING] Skipped: {e}")

        # ==========================================================
        # MERGE: web-user (phone, no tg_id) → tg-user (tg_id + phone)
        # ==========================================================
        if obj.tg_id:
            web_user = (
                db.query(DBUsers)
                .filter(
                    DBUsers.phone == phone,
                    DBUsers.is_active == 1,
                    DBUsers.tg_id.is_(None),
                    DBUsers.id != obj.id,
                )
                .first()
            )
            if web_user:
                _merge_web_user_into(db, source=web_user, target=obj)

    # ==========================================================
    # Apply changes
    # ==========================================================
    for field, value in update_data.items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBUsers, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()

