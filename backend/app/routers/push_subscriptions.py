# backend/app/routers/push_subscriptions.py
# API.md: PATCH = 405, DELETE = ALLOWED (hard)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import PushSubscriptions as DBPushSubscriptions
from ..schemas.push_subscriptions import (
    PushSubscriptionCreate,
    PushSubscriptionRead,
)

router = APIRouter(prefix="/push_subscriptions", tags=["push_subscriptions"])


@router.get("/", response_model=list[PushSubscriptionRead])
def list_push_subscriptions(db: Session = Depends(get_db)):
    return db.query(DBPushSubscriptions).all()


@router.get("/{id}", response_model=PushSubscriptionRead)
def get_push_subscription(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBPushSubscriptions, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=PushSubscriptionRead, status_code=status.HTTP_201_CREATED
)
def create_push_subscription(
    data: PushSubscriptionCreate,
    db: Session = Depends(get_db),
):
    obj = DBPushSubscriptions(**data.model_dump())
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
def delete_push_subscription(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBPushSubscriptions, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()

