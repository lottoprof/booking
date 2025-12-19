# backend/app/routers/client_packages.py
# API.md: PATCH = 405, DELETE = ALLOWED (hard)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import ClientPackages as DBClientPackages
from ..schemas.client_packages import (
    ClientPackageCreate,
    ClientPackageRead,
)

router = APIRouter(prefix="/client_packages", tags=["client_packages"])


@router.get("/", response_model=list[ClientPackageRead])
def list_client_packages(db: Session = Depends(get_db)):
    return db.query(DBClientPackages).all()


@router.get("/{id}", response_model=ClientPackageRead)
def get_client_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBClientPackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=ClientPackageRead, status_code=status.HTTP_201_CREATED
)
def create_client_package(
    data: ClientPackageCreate,
    db: Session = Depends(get_db),
):
    obj = DBClientPackages(**data.model_dump())
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
def delete_client_package(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBClientPackages, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()

