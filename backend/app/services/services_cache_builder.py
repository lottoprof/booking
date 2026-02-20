# backend/app/services/services_cache_builder.py
"""
Build PricingCard dicts from DB.

Reused by:
- GET /services/web endpoint
- rebuild_services_cache() (write-through cache)
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from ..models.generated import Services as DBServices, ServicePackages as DBServicePackages
from .package_pricing import calc_package_price
from .slug import slugify

# service_id → unicode icon (single-service packages)
_ICON_MAP: dict[int, str] = {
    1: "✦",   # LPG
    2: "◎",   # Сфера
    3: "◎",   # Сфера
    4: "◇",   # Прессотерапия
    5: "❋",   # Обёртывание
    6: "≋",   # Indiba
    7: "≋",   # Indiba
}
_ICON_COMBO = "◈"  # composite packages


def build_pricing_cards(db: Session, view: Optional[str] = None) -> list[dict]:
    """
    Build PricingCard dicts grouped by package name.

    view=pricing  → packages with show_on_pricing=1
    default       → packages with show_on_booking=1
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

    # Group ALL packages by name → list of (pkg, items, price)
    # Then keep only groups where at least one package is visible.
    all_cards: dict[str, list[tuple]] = {}
    visible_names: set[str] = set()
    for pkg in packages:
        try:
            items = json.loads(pkg.package_items) if pkg.package_items else []
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(items, list) or not items:
            continue

        pkg_price = calc_package_price(items, services_map)
        if pkg_price is None:
            continue

        all_cards.setdefault(pkg.name, []).append((pkg, items, pkg_price))
        if getattr(pkg, visibility_attr, True):
            visible_names.add(pkg.name)

    cards = {name: group for name, group in all_cards.items() if name in visible_names}

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

        description = first_pkg.description

        variants = []
        for pkg, items, price in pkg_group:
            qty = items[0].get("quantity", 1)

            if qty == 1:
                variants.append({
                    "label": "Разовый сеанс",
                    "qty": 1,
                    "price": price,
                    "package_id": pkg.id,
                })
            else:
                per_session = round(price / qty)
                full = sum(
                    services_map[it["service_id"]].price * it.get("quantity", 1)
                    for it in items
                    if it.get("service_id") in services_map
                )
                old_price = full if full > price else None
                variants.append({
                    "label": f"{qty} сеансов",
                    "qty": qty,
                    "price": price,
                    "old_price": old_price,
                    "per_session": per_session,
                    "package_id": pkg.id,
                })

        result.append({
            "name": card_name,
            "slug": slugify(card_name),
            "service_id": first_sid,
            "description": description,
            "category": category,
            "icon": _ICON_MAP.get(first_sid, _ICON_COMBO) if len(first_items) == 1 else _ICON_COMBO,
            "duration_min": total_duration,
            "variants": variants,
        })

    return result


def build_pricing_cards_json(db: Session, view: Optional[str] = None) -> str:
    """Build and serialize to JSON string for Redis storage."""
    cards = build_pricing_cards(db, view)
    return json.dumps(cards, ensure_ascii=False)
