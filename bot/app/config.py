from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    TG_BOT_TOKEN: str
    SUPPORT_TG_ID: int | None = None
    CHANNEL_URL: str | None = None
    MINIAPP_URL: str | None = None
    TG_CHANNEL_PUBLIC_ID: str | None = None
    TG_CHANNEL_DRAFT_ID: str | None = None
    TG_PROXY_URL: str | None = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
    )


settings = Settings()

BOT_TOKEN = settings.TG_BOT_TOKEN
SUPPORT_TG_ID = settings.SUPPORT_TG_ID
CHANNEL_URL = settings.CHANNEL_URL
MINIAPP_URL = settings.MINIAPP_URL
TG_CHANNEL_PUBLIC_ID = settings.TG_CHANNEL_PUBLIC_ID
TG_CHANNEL_DRAFT_ID = settings.TG_CHANNEL_DRAFT_ID
TG_PROXY_URL = settings.TG_PROXY_URL
