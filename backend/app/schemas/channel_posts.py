from pydantic import BaseModel


class ChannelPostCreate(BaseModel):
    draft_message_id: int
    draft_chat_id: int
    draft_text: str | None = None
    media_group_id: str | None = None
    media_files: str | None = None
    status: str = "draft"

    model_config = {"from_attributes": True}


class ChannelPostUpdate(BaseModel):
    draft_text: str | None = None
    media_files: str | None = None
    cta_buttons: str | None = None
    hashtags: str | None = None
    scheduled_at: str | None = None
    published_at: str | None = None
    public_message_id: int | None = None
    public_chat_id: int | None = None
    status: str | None = None

    model_config = {"from_attributes": True}


class ChannelPostRead(BaseModel):
    id: int
    draft_message_id: int
    draft_chat_id: int
    draft_text: str | None = None
    media_group_id: str | None = None
    media_files: str | None = None
    public_message_id: int | None = None
    public_chat_id: int | None = None
    cta_buttons: str | None = None
    hashtags: str | None = None
    scheduled_at: str | None = None
    published_at: str | None = None
    status: str
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}
