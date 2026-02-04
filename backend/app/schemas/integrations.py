# backend/app/schemas/integrations.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class IntegrationStatusRead(BaseModel):
    """Read schema for specialist integration status."""
    specialist_id: int
    provider: str
    is_connected: bool
    sync_enabled: bool
    sync_scope: Optional[str] = "own"
    calendar_id: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IntegrationRead(BaseModel):
    """Full integration read schema (internal use)."""
    id: int
    specialist_id: int
    provider: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    calendar_id: Optional[str] = None
    sync_enabled: int
    last_sync_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IntegrationUpdate(BaseModel):
    """Update schema for integration settings."""
    sync_enabled: Optional[int] = None
    calendar_id: Optional[str] = None

    model_config = {"from_attributes": True}


class OAuthCallbackResponse(BaseModel):
    """Response from OAuth callback processing."""
    success: bool
    specialist_id: int
    message: str


class BookingExternalEventRead(BaseModel):
    """Read schema for booking external event link."""
    id: int
    booking_id: int
    provider: str
    external_event_id: str
    specialist_integration_id: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
