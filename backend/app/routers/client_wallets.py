# backend/app/routers/client_wallets.py
# API.md: PATCH = ALLOWED (is_blocked), DELETE = 405

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import ClientWallets as DBClientWallets
from ..schemas.client_wallets import (
    ClientWalletCreate,
    ClientWalletUpdate,
    ClientWalletRead,
)

router = APIRouter(prefix="/client_wallets", tags=["client_wallets"])


@router.get("/", response_model=list[ClientWalletRead])
def list_client_wallets(db: Session = Depends(get_db)):
    return db.query(DBClientWallets).all()


@router.get("/{id}", response_model=ClientWalletRead)
def get_client_wallet(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBClientWallets, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=ClientWalletRead, status_code=status.HTTP_201_CREATED
)
def create_client_wallet(
    data: ClientWalletCreate,
    db: Session = Depends(get_db),
):
    obj = DBClientWallets(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=ClientWalletRead)
def update_client_wallet(
    id: int,
    data: ClientWalletUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBClientWallets, id)
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

