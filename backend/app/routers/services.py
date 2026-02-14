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
    PricingCard,
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


@router.get("/web", response_model=list[PricingCard])
def list_services_web(
    view: Optional[str] = Query(None, description="pricing or booking"),
    db: Session = Depends(get_db),
):
    """
    Pricing cards grouped by package name.

    Each unique package name becomes a card; each qty level (1/5/10)
    becomes a variant inside that card.

    view=pricing → packages with show_on_pricing=1
    default      → packages with show_on_booking=1
    """
    services = (
        db.query(DBServices)
        .filter(DBServices.is_active == 1)
        .all()
    )
    services_map = {s.id: s for s in services}

    packages = (
        db.query(DBServicePackages)
        .filter(DBServicePackages.is_active == 1)
        .all()
    )

    visibility_attr = "show_on_pricing" if view == "pricing" else "show_on_booking"

    # Group packages by name → list of (pkg, items, price)
    cards: dict[str, list[tuple]] = {}
    for pkg in packages:
        if not getattr(pkg, visibility_attr, True):
            continue
        try:
            items = json.loads(pkg.package_items) if pkg.package_items else []
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(items, list) or not items:
            continue

        pkg_price = calc_package_price(items, services_map)
        if pkg_price is None:
            continue

        cards.setdefault(pkg.name, []).append((pkg, items, pkg_price))

    result = []
    for card_name, pkg_group in cards.items():
        # Sort by qty so variants are ordered 1 → 5 → 10
        pkg_group.sort(key=lambda t: t[1][0].get("quantity", 1))

        # Derive card metadata from first package's items
        first_pkg, first_items, _ = pkg_group[0]
        first_sid = first_items[0].get("service_id")
        first_svc = services_map.get(first_sid)

        # Determine category & duration from constituent services
        svc_categories = set()
        total_duration = 0
        for item in first_items:
            svc = services_map.get(item.get("service_id"))
            if svc:
                if svc.category:
                    svc_categories.add(svc.category)
                total_duration += svc.duration_min

        category = first_svc.category if first_svc and len(first_items) == 1 else None
        if len(svc_categories) == 1:
            category = svc_categories.pop()

        description = first_pkg.description or (first_svc.description if first_svc else None)

        variants = []
        for pkg, items, price in pkg_group:
            qty = items[0].get("quantity", 1)

            if qty == 1:
                variants.append(ServiceVariant(
                    label="Разовый сеанс",
                    qty=1,
                    price=price,
                ))
            else:
                per_session = round(price / qty)
                full = sum(
                    services_map[it["service_id"]].price * it.get("quantity", 1)
                    for it in items
                    if it.get("service_id") in services_map
                )
                old_price = full if full > price else None
                variants.append(ServiceVariant(
                    label=f"{qty} сеансов",
                    qty=qty,
                    price=price,
                    old_price=old_price,
                    per_session=per_session,
                ))

        result.append(PricingCard(
            name=card_name,
            slug=slugify(card_name),
            description=description,
            category=category,
            icon="✦",
            duration_min=total_duration,
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

