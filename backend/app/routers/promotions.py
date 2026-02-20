# backend/app/routers/promotions.py

import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Promotions as DBPromotions
from ..schemas.promotions import (
    PromotionCreate,
    PromotionRead,
    PromotionUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/promotions", tags=["promotions"])


def _trigger_render():
    """Fire-and-forget SSG re-render after promo data changes."""
    from backend.app.services.ssg.render_promo import render_promo_all

    try:
        threading.Thread(target=render_promo_all, daemon=True).start()
    except Exception:
        logger.exception("Failed to trigger promo render")


@router.get("/", response_model=list[PromotionRead])
def list_promotions(db: Session = Depends(get_db)):
    return db.query(DBPromotions).order_by(DBPromotions.sort_order).all()


@router.get("/{id}", response_model=PromotionRead)
def get_promotion(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBPromotions, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=PromotionRead, status_code=status.HTTP_201_CREATED
)
def create_promotion(
    data: PromotionCreate,
    db: Session = Depends(get_db),
):
    obj = DBPromotions(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    _trigger_render()
    return obj


@router.patch("/{id}", response_model=PromotionRead)
def update_promotion(
    id: int,
    data: PromotionUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBPromotions, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    obj.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    db.refresh(obj)
    _trigger_render()
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBPromotions, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()
    _trigger_render()
