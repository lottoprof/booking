# backend/app/routers/client_packages.py
# API.md: PATCH = 405, DELETE = ALLOWED (hard)

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import (
    ClientPackages as DBClientPackages,
    ServicePackages as DBServicePackages,
)
from ..schemas.client_packages import (
    ClientPackageCreate,
    ClientPackageRead,
    ClientPackageWithRemaining,
)

router = APIRouter(prefix="/client_packages", tags=["client_packages"])


@router.get("/", response_model=list[ClientPackageRead])
def list_client_packages(db: Session = Depends(get_db)):
    return db.query(DBClientPackages).all()


@router.get("/{id}", response_model=ClientPackageRead)
def get_client_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBClientPackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=ClientPackageRead, status_code=status.HTTP_201_CREATED
)
def create_client_package(
    data: ClientPackageCreate,
    db: Session = Depends(get_db),
):
    obj = DBClientPackages(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}")
def patch_not_allowed():
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed",
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBClientPackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()


def _calculate_remaining(
    package_items: str,
    used_items: str,
) -> tuple[dict, int, int]:
    """
    Calculate remaining services in a package.

    Returns:
        (remaining_items, total_quantity, total_remaining)
    """
    items = json.loads(package_items) if package_items else []
    used = json.loads(used_items) if used_items else {}

    remaining_items = {}
    total_quantity = 0
    total_remaining = 0

    for item in items:
        service_id = str(item["service_id"])
        quantity = item["quantity"]
        used_count = used.get(service_id, 0)
        remaining = quantity - used_count

        remaining_items[service_id] = remaining
        total_quantity += quantity
        total_remaining += remaining

    return remaining_items, total_quantity, total_remaining


@router.get("/user/{user_id}", response_model=list[ClientPackageWithRemaining])
def get_user_packages(
    user_id: int,
    include_closed: bool = Query(False, description="Include closed packages"),
    db: Session = Depends(get_db),
):
    """
    Get all packages for a user with remaining service counts.

    By default excludes closed packages. Use include_closed=true to include them.
    Active packages are returned first (valid_to IS NULL or valid_to >= today),
    sorted by valid_to ASC (expiring soonest first).
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")

    query = db.query(DBClientPackages).filter(DBClientPackages.user_id == user_id)

    if not include_closed:
        query = query.filter(DBClientPackages.is_closed == 0)

    # Order: active first (valid_to is null or >= today), then by valid_to ASC
    packages = query.all()

    result = []
    for cp in packages:
        # Get service package info
        sp = db.get(DBServicePackages, cp.package_id)
        if not sp:
            continue

        remaining_items, total_quantity, total_remaining = _calculate_remaining(
            sp.package_items,
            cp.used_items,
        )

        result.append(ClientPackageWithRemaining(
            id=cp.id,
            user_id=cp.user_id,
            package_id=cp.package_id,
            used_quantity=cp.used_quantity,
            used_items=cp.used_items,
            is_closed=bool(cp.is_closed),
            purchased_at=cp.purchased_at,
            valid_to=cp.valid_to,
            notes=cp.notes,
            package_name=sp.name,
            package_price=sp.package_price,
            remaining_items=remaining_items,
            total_quantity=total_quantity,
            total_remaining=total_remaining,
        ))

    # Sort: active packages first (valid_to is None or >= today), then by valid_to ASC
    def sort_key(p):
        if p.valid_to is None:
            return (1, "9999-99-99")  # Active with no expiry - last among active
        valid_to_str = str(p.valid_to)[:10] if p.valid_to else "9999-99-99"
        is_active = 0 if valid_to_str >= today else 1
        return (is_active, valid_to_str)

    result.sort(key=sort_key)
    return result


@router.get("/{id}/remaining")
def get_package_remaining(id: int, db: Session = Depends(get_db)):
    """
    Get remaining service counts for a specific client package.

    Returns detailed breakdown of used and remaining for each service in the package.
    """
    cp = db.get(DBClientPackages, id)
    if not cp:
        raise HTTPException(status_code=404, detail="Client package not found")

    sp = db.get(DBServicePackages, cp.package_id)
    if not sp:
        raise HTTPException(status_code=404, detail="Service package not found")

    items = json.loads(sp.package_items) if sp.package_items else []
    used = json.loads(cp.used_items) if cp.used_items else {}

    breakdown = []
    total_quantity = 0
    total_used = 0
    total_remaining = 0

    for item in items:
        service_id = item["service_id"]
        quantity = item["quantity"]
        used_count = used.get(str(service_id), 0)
        remaining = quantity - used_count

        breakdown.append({
            "service_id": service_id,
            "quantity": quantity,
            "used": used_count,
            "remaining": remaining,
        })

        total_quantity += quantity
        total_used += used_count
        total_remaining += remaining

    return {
        "client_package_id": cp.id,
        "package_id": sp.id,
        "package_name": sp.name,
        "is_closed": bool(cp.is_closed),
        "valid_to": cp.valid_to,
        "breakdown": breakdown,
        "total_quantity": total_quantity,
        "total_used": total_used,
        "total_remaining": total_remaining,
    }

