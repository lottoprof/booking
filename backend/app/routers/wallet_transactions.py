# backend/app/routers/wallet_transactions.py
# API.md: READ-ONLY, PATCH = 405, DELETE = 405, POST = 405

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import WalletTransactions as DBWalletTransactions
from ..schemas.wallet_transactions import WalletTransactionRead

router = APIRouter(prefix="/wallet_transactions", tags=["wallet_transactions"])


@router.get("/", response_model=list[WalletTransactionRead])
def list_wallet_transactions(db: Session = Depends(get_db)):
    return db.query(DBWalletTransactions).all()


@router.get("/{id}", response_model=WalletTransactionRead)
def get_wallet_transaction(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBWalletTransactions, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/")
def post_not_allowed():
    raise HTTPException(status_code=405, detail="Method not allowed")


@router.patch("/{id}")
def patch_not_allowed():
    raise HTTPException(status_code=405, detail="Method not allowed")


@router.delete("/{id}")
def delete_not_allowed():
    raise HTTPException(status_code=405, detail="Method not allowed")

