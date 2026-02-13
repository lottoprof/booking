# backend/app/routers/services.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Services as DBServices, ServicePackages as DBServicePackages
from ..schemas.services import (
    ServiceCreate,
    ServiceUpdate,
    ServiceRead,
    ServiceVariant,
    ServiceWebRead,
)
from ..services.package_pricing import calc_package_price
from ..services.slug import slugify
from ..services.web_cache import invalidate_services_cache

router = APIRouter(prefix="/services", tags=["services"])


@router.get("/", response_model=list[ServiceRead])
def list_services(db: Session = Depends(get_db)):
    return (
        db.query(DBServices)
        .filter(DBServices.is_active == 1)
        .all()
    )


@router.get("/web", response_model=list[ServiceWebRead])
def list_services_web(
    view: Optional[str] = Query(None, description="pricing or booking"),
    db: Session = Depends(get_db),
):
    """
    Services enriched with package variants for web frontend.

    view=pricing → packages with show_on_pricing=1
    default      → packages with show_on_booking=1
    """
    services = (
        db.query(DBServices)
        .filter(DBServices.is_active == 1)
        .all()
    )
    services_map = {s.id: s for s in services}

    # Fetch active packages
    packages = (
        db.query(DBServicePackages)
        .filter(DBServicePackages.is_active == 1)
        .all()
    )

    # Filter by visibility
    visibility_attr = "show_on_pricing" if view == "pricing" else "show_on_booking"

    # Build service_id → package variants mapping
    svc_packages: dict[int, list[dict]] = {}
    for pkg in packages:
        if not getattr(pkg, visibility_attr, True):
            continue
        try:
            items = json.loads(pkg.package_items) if pkg.package_items else []
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(items, list):
            continue

        # Compute package price via tier logic
        pkg_price = calc_package_price(items, services_map)

        for item in items:
            sid = item.get("service_id")
            qty = item.get("quantity", 1)
            if not sid:
                continue
            svc = services_map.get(sid)
            if not svc:
                continue
            # Compute total duration for this service in the package
            total_dur = svc.duration_min * qty
            svc_packages.setdefault(sid, []).append({
                "name": pkg.name,
                "price": pkg_price or 0,
                "qty": qty,
                "total_duration_min": total_dur,
            })

    result = []
    for s in services:
        base_price = s.price
        variants = [ServiceVariant(label="Разовый сеанс", price=base_price)]

        for pkg in svc_packages.get(s.id, []):
            qty = pkg["qty"]
            per_session = round(pkg["price"] / qty) if qty > 0 else pkg["price"]
            old_price = base_price * qty if pkg["price"] < base_price * qty else None
            variants.append(ServiceVariant(
                label=pkg["name"],
                qty=qty,
                price=pkg["price"],
                old_price=old_price,
                per_session=per_session,
                total_duration_min=pkg.get("total_duration_min"),
            ))

        result.append(ServiceWebRead(
            id=s.id,
            name=s.name,
            slug=slugify(s.name),
            description=s.description,
            category=s.category,
            icon="✦",
            duration_min=s.duration_min,
            price=base_price,
            variants=variants,
        ))

    return result


@router.get("/{id}", response_model=ServiceRead)
def get_service(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServices, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    data: ServiceCreate,
    db: Session = Depends(get_db),
):
    obj = DBServices(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    invalidate_services_cache()
    return obj


@router.patch("/{id}", response_model=ServiceRead)
def update_service(
    id: int,
    data: ServiceUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBServices, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    invalidate_services_cache()
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServices, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()
    invalidate_services_cache()

