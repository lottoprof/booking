import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.generated import ChannelPosts as DBChannelPosts
from ..schemas.channel_posts import (
    ChannelPostCreate,
    ChannelPostRead,
    ChannelPostUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channel-posts", tags=["channel-posts"])


@router.get("/", response_model=list[ChannelPostRead])
def list_channel_posts(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    q = db.query(DBChannelPosts)
    if status_filter:
        q = q.filter(DBChannelPosts.status == status_filter)
    return q.order_by(DBChannelPosts.created_at.desc()).all()


@router.get("/pending", response_model=list[ChannelPostRead])
def list_pending(db: Session = Depends(get_db)):
    """Posts with scheduled_at <= now and status=scheduled."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return (
        db.query(DBChannelPosts)
        .filter(
            DBChannelPosts.status == "scheduled",
            DBChannelPosts.scheduled_at <= now,
        )
        .order_by(DBChannelPosts.scheduled_at)
        .all()
    )


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """List blog categories for hashtag selection."""
    from sqlalchemy import text as sa_text

    rows = db.execute(
        sa_text("SELECT id, slug, name FROM categories ORDER BY sort_order")
    ).fetchall()
    return [{"id": r[0], "slug": r[1], "name": r[2]} for r in rows]


@router.get("/articles")
def list_articles(db: Session = Depends(get_db)):
    """List published articles for CTA button selection."""
    from sqlalchemy import text as sa_text

    rows = db.execute(
        sa_text(
            "SELECT slug, title FROM articles"
            " WHERE is_published = 1"
            " ORDER BY sort_order"
        )
    ).fetchall()
    return [{"slug": r[0], "title": r[1]} for r in rows]


@router.get("/{post_id}", response_model=ChannelPostRead)
def get_channel_post(post_id: int, db: Session = Depends(get_db)):
    obj = db.get(DBChannelPosts, post_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.post(
    "/", response_model=ChannelPostRead, status_code=status.HTTP_201_CREATED
)
def create_channel_post(
    data: ChannelPostCreate,
    db: Session = Depends(get_db),
):
    obj = DBChannelPosts(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{post_id}", response_model=ChannelPostRead)
def update_channel_post(
    post_id: int,
    data: ChannelPostUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(DBChannelPosts, post_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    obj.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    db.refresh(obj)
    return obj
