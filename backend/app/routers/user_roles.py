# backend/app/routers/user_roles.py
# API.md: PATCH = 405, DELETE = ALLOWED (hard)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import UserRoles as DBUserRoles
from ..schemas.user_roles import (
    UserRoleCreate,
    UserRoleRead,
)

router = APIRouter(prefix="/user_roles", tags=["user_roles"])


@router.get("/", response_model=list[UserRoleRead])
def list_user_roles(db: Session = Depends(get_db)):
    return db.query(DBUserRoles).all()


@router.get("/{id}", response_model=UserRoleRead)
def get_user_role(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBUserRoles, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post("/", response_model=UserRoleRead, status_code=status.HTTP_201_CREATED)
def create_user_role(
    data: UserRoleCreate,
    db: Session = Depends(get_db),
):
    obj = DBUserRoles(**data.model_dump())
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
def delete_user_role(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBUserRoles, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()

