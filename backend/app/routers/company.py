# backend/app/routers/company.py
# API.md: PATCH = ALLOWED, DELETE = 405

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Company as DBCompany
from ..schemas.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyRead,
)

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db)):
    return db.query(DBCompany).all()


@router.get("/{id}", response_model=CompanyRead)
def get_company(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBCompany, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
):
    obj = DBCompany(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=CompanyRead)
def update_company(
    id: int,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBCompany, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}")
def delete_not_allowed():
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Method not allowed",
    )

