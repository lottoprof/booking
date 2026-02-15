# backend/app/routers/services.py
# API.md: PATCH = ALLOWED, DELETE = soft-delete (is_active)

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Services as DBServices
from ..schemas.services import (
    ServiceCreate,
    ServiceUpdate,
    ServiceRead,
    PricingCard,
)
from ..services.services_cache_builder import build_pricing_cards
from ..services.web_cache import rebuild_services_cache

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
    return build_pricing_cards(db, view)


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
    rebuild_services_cache(db)
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
    rebuild_services_cache(db)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBServices, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()
    rebuild_services_cache(db)

