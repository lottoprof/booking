# backend/app/services/package_pricing.py
"""
Dynamic package price calculation.

package_price is NOT stored in service_packages — it is computed from
price_5/price_10 of the constituent services + package_items quantities.
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from ..models.generated import Services as DBService, ServicePackages as DBServicePackage


def calc_package_price(
    package_items: list[dict],
    services: dict[int, DBService],
) -> Optional[float]:
    """
    Calculate dynamic package price from service tiers.

    Args:
        package_items: list of {"service_id": int, "quantity": int}
        services: {service_id: DBService} lookup

    Returns:
        Computed price or None if data is insufficient.

    Tier logic (per-item quantity, NOT sum):
        qty = 1       → service.price
        qty 2..5      → service.price_5 (fallback to price)
        qty 6..10     → service.price_10 (fallback to price_5, then price)
    """
    if not package_items:
        return None

    total = 0.0

    for item in package_items:
        sid = item.get("service_id")
        qty = item.get("quantity", 1)
        svc = services.get(sid)
        if not svc:
            return None

        unit_price = _tier_price(svc, qty)
        total += qty * unit_price

    return round(total, 2)


def _tier_price(service: DBService, qty: int) -> float:
    """Pick the right tier price for a service given its quantity."""
    if qty <= 1:
        return service.price
    elif qty <= 5:
        return service.price_5 if service.price_5 is not None else service.price
    else:
        if service.price_10 is not None:
            return service.price_10
        if service.price_5 is not None:
            return service.price_5
        return service.price


def calc_package_duration(
    package_items: list[dict],
    services: dict[int, DBService],
) -> Optional[int]:
    """Sum of duration_min for unique services in package (no breaks)."""
    if not package_items:
        return None
    seen = set()
    total = 0
    for item in package_items:
        sid = item.get("service_id")
        svc = services.get(sid)
        if not svc:
            return None
        if sid not in seen:
            seen.add(sid)
            total += svc.duration_min
    return total


def _load_items_and_services(
    package_items_json: str,
    db: Session,
) -> tuple[Optional[list[dict]], Optional[dict[int, DBService]]]:
    """Parse package_items JSON and load corresponding services from DB."""
    try:
        items = json.loads(package_items_json) if package_items_json else []
    except (json.JSONDecodeError, TypeError):
        return None, None

    if not isinstance(items, list) or not items:
        return None, None

    service_ids = [item["service_id"] for item in items if "service_id" in item]
    if not service_ids:
        return None, None

    services_list = (
        db.query(DBService)
        .filter(DBService.id.in_(service_ids))
        .all()
    )
    services_map = {s.id: s for s in services_list}
    return items, services_map


def build_package_description(
    package_items_json: str,
    db: Session,
) -> Optional[str]:
    """
    Auto-build description from constituent services.

    Formula: ", ".join(svc.name + " " + svc.description) for unique services.
    """
    result = _load_items_and_services(package_items_json, db)
    if result[0] is None:
        return None
    items, services_map = result

    seen = set()
    parts = []
    for item in items:
        sid = item.get("service_id")
        if sid in seen:
            continue
        seen.add(sid)
        svc = services_map.get(sid)
        if not svc:
            continue
        part = svc.name
        if svc.description:
            part += " " + svc.description
        parts.append(part)

    return ", ".join(parts) if parts else None


def enrich_package(
    package: DBServicePackage,
    db: Session,
) -> tuple[Optional[float], Optional[int]]:
    """
    Compute (package_price, total_duration_min) for a service_package row.
    """
    result = _load_items_and_services(package.package_items, db)
    if result[0] is None:
        return None, None
    items, services_map = result

    price = calc_package_price(items, services_map)
    duration = calc_package_duration(items, services_map)
    return price, duration


def enrich_package_price(
    package: DBServicePackage,
    db: Session,
) -> Optional[float]:
    """Backwards-compatible wrapper: returns only package_price."""
    price, _ = enrich_package(package, db)
    return price
