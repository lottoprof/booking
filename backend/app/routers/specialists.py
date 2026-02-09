# backend/app/routers/specialists.py
# API.md:
# - PATCH = ALLOWED
# - DELETE = soft-delete (is_active)
# - Domain relation: specialists -> services

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text

from ..database import get_db
from ..models.generated import Specialists as DBSpecialists
from ..schemas.specialists import (
    SpecialistCreate,
    SpecialistUpdate,
    SpecialistRead,
)

router = APIRouter(prefix="/specialists", tags=["specialists"])


# ---------------------------------------------------------------------
# Base CRUD
# ---------------------------------------------------------------------

@router.get("/", response_model=list[SpecialistRead])
def list_specialists(db: Session = Depends(get_db)):
    specs = (
        db.query(DBSpecialists)
        .options(joinedload(DBSpecialists.user))
        .filter(DBSpecialists.is_active == 1)
        .all()
    )
    for s in specs:
        if not s.display_name and s.user:
            s.display_name = s.user.first_name
    return specs


@router.get("/{id}", response_model=SpecialistRead)
def get_specialist(id: int, db: Session = Depends(get_db)):
    obj = (
        db.query(DBSpecialists)
        .options(joinedload(DBSpecialists.user))
        .filter(DBSpecialists.id == id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    if not obj.display_name and obj.user:
        obj.display_name = obj.user.first_name
    return obj


@router.post("/", response_model=SpecialistRead, status_code=status.HTTP_201_CREATED)
def create_specialist(
    data: SpecialistCreate,
    db: Session = Depends(get_db),
):
    obj = DBSpecialists(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{id}", response_model=SpecialistRead)
def update_specialist(
    id: int,
    data: SpecialistUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBSpecialists, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_specialist(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBSpecialists, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    obj.is_active = 0
    db.commit()


# ---------------------------------------------------------------------
# Domain: Specialist → Services
# ---------------------------------------------------------------------

@router.get("/{id}/services")
def list_specialist_services(id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text(
            """
            SELECT
                ss.service_id,
                ss.is_default,
                ss.is_active,
                ss.notes
            FROM specialist_services ss
            WHERE ss.specialist_id = :sid
              AND ss.is_active = 1
            """
        ),
        {"sid": id},
    )
    return result.mappings().all()


@router.post("/{id}/services", status_code=status.HTTP_201_CREATED)
def add_service_to_specialist(
    id: int,
    payload: dict,  # service_id, is_default?, notes?
    db: Session = Depends(get_db),
):
    if "service_id" not in payload:
        raise HTTPException(status_code=400, detail="service_id is required")

    db.execute(
        text(
            """
            INSERT INTO specialist_services
                (specialist_id, service_id, is_default, notes)
            VALUES
                (:sid, :service_id, :is_default, :notes)
            """
        ),
        {
            "sid": id,
            "service_id": payload["service_id"],
            "is_default": payload.get("is_default", 0),
            "notes": payload.get("notes"),
        },
    )
    db.commit()


@router.patch("/{id}/services/{service_id}")
def update_specialist_service(
    id: int,
    service_id: int,
    payload: dict,  # is_active?, is_default?, notes?
    db: Session = Depends(get_db),
):
    allowed = {"is_active", "is_default", "notes"}
    fields = {k: v for k, v in payload.items() if k in allowed}

    if not fields:
        raise HTTPException(status_code=400, detail="No valid fields")

    set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())

    db.execute(
        text(
            f"""
            UPDATE specialist_services
            SET {set_clause}
            WHERE specialist_id = :sid
              AND service_id = :service_id
            """
        ),
        {"sid": id, "service_id": service_id, **fields},
    )
    db.commit()


@router.delete("/{id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_specialist_service(
    id: int,
    service_id: int,
    db: Session = Depends(get_db),
):
    db.execute(
        text(
            """
            UPDATE specialist_services
            SET is_active = 0
            WHERE specialist_id = :sid
              AND service_id = :service_id
            """
        ),
        {"sid": id, "service_id": service_id},
    )
    db.commit()

