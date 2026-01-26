from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import NotificationSettings as DBNotificationSettings
from ..schemas.notification_settings import (
    NotificationSettingsCreate,
    NotificationSettingsUpdate,
    NotificationSettingsRead,
)

router = APIRouter(prefix="/notification_settings", tags=["notification_settings"])


@router.get("/", response_model=list[NotificationSettingsRead])
def list_notification_settings(
    company_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    recipient_role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(DBNotificationSettings)

    if company_id is not None:
        query = query.filter(DBNotificationSettings.company_id == company_id)
    if event_type is not None:
        query = query.filter(DBNotificationSettings.event_type == event_type)
    if recipient_role is not None:
        query = query.filter(DBNotificationSettings.recipient_role == recipient_role)

    return query.all()


@router.get("/{id}", response_model=NotificationSettingsRead)
def get_notification_setting(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBNotificationSettings, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/",
    response_model=NotificationSettingsRead,
    status_code=status.HTTP_201_CREATED,
)
def create_notification_setting(
    data: NotificationSettingsCreate,
    db: Session = Depends(get_db),
):
    obj = DBNotificationSettings(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=NotificationSettingsRead)
def update_notification_setting(
    id: int,
    data: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBNotificationSettings, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_setting(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBNotificationSettings, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()
