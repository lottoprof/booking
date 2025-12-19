# backend/app/routers/roles.py
# API.md: READ-ONLY, PATCH = 405, DELETE = 405, POST = 405

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import Roles as DBRoles
from ..schemas.roles import RoleRead

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("/", response_model=list[RoleRead])
def list_roles(db: Session = Depends(get_db)):
    return db.query(DBRoles).all()


@router.get("/{id}", response_model=RoleRead)
def get_role(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBRoles, id)
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

