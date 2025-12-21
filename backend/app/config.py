# backend/app/config.py

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # /git/booking


class Settings(BaseSettings):
    # backend-only
    database_url: str
    redis_url: str

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",   # Читаем только свои переменные 
    )


settings = Settings()

