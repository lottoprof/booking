from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import AuditLog as DBAuditLog
from ..schemas.audit_log import AuditLogRead


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", response_model=list[AuditLogRead])
def list_audit(
    event_type: Optional[str] = None,
    target_user_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Read-only audit log.

    Filters:
    - event_type (exact match)
    - target_user_id
    - limit (default 50, max enforced here)
    """
    q = db.query(DBAuditLog)

    if event_type:
        q = q.filter(DBAuditLog.event_type == event_type)

    if target_user_id:
        q = q.filter(DBAuditLog.target_user_id == target_user_id)

    return (
        q.order_by(DBAuditLog.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )


@router.get("/{id}", response_model=AuditLogRead)
def get_audit(id: int, db: Session = Depends(get_db)):
    obj = db.get(DBAuditLog, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj

