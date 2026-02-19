# backend/app/schemas/promotions.py

from pydantic import BaseModel


class PromotionCreate(BaseModel):
    badge_type: str = "sale"
    badge_text: str
    title: str
    description: str
    price_new: int | None = None
    price_old: int | None = None
    end_date: str | None = None
    cta_text: str | None = None
    cta_url: str | None = None
    is_active: int = 1
    sort_order: int = 0

    model_config = {"from_attributes": True}


class PromotionUpdate(BaseModel):
    badge_type: str | None = None
    badge_text: str | None = None
    title: str | None = None
    description: str | None = None
    price_new: int | None = None
    price_old: int | None = None
    end_date: str | None = None
    cta_text: str | None = None
    cta_url: str | None = None
    is_active: int | None = None
    sort_order: int | None = None

    model_config = {"from_attributes": True}


class PromotionRead(BaseModel):
    id: int
    badge_type: str
    badge_text: str
    title: str
    description: str
    price_new: int | None = None
    price_old: int | None = None
    end_date: str | None = None
    cta_text: str | None = None
    cta_url: str | None = None
    is_active: int
    sort_order: int
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}
