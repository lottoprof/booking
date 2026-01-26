from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import AdTemplates as DBAdTemplates
from ..schemas.ad_templates import (
    AdTemplateCreate,
    AdTemplateUpdate,
    AdTemplateRead,
)

router = APIRouter(prefix="/ad_templates", tags=["ad_templates"])


@router.get("/", response_model=list[AdTemplateRead])
def list_ad_templates(db: Session = Depends(get_db)):
    return (
        db.query(DBAdTemplates)
        .filter(DBAdTemplates.active == 1)
        .all()
    )


@router.get("/{id}", response_model=AdTemplateRead)
def get_ad_template(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBAdTemplates, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/",
    response_model=AdTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ad_template(
    data: AdTemplateCreate,
    db: Session = Depends(get_db),
):
    obj = DBAdTemplates(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=AdTemplateRead)
def update_ad_template(
    id: int,
    data: AdTemplateUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBAdTemplates, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ad_template(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBAdTemplates, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.active = 0
    db.commit()
