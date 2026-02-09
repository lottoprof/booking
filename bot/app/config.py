from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    TG_BOT_TOKEN: str
    SUPPORT_TG_ID: Optional[int] = None
    CHANNEL_URL: Optional[str] = None
    MINIAPP_URL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
    )


settings = Settings()

BOT_TOKEN = settings.TG_BOT_TOKEN
SUPPORT_TG_ID = settings.SUPPORT_TG_ID
CHANNEL_URL = settings.CHANNEL_URL
MINIAPP_URL = settings.MINIAPP_URL
