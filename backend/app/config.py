# backend/app/config.py

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # /booking


class Settings(BaseSettings):
    database_url: str
    redis_url: str

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:///./"):
            # Преобразуем относительный путь в абсолютный
            relative_path = url.replace("sqlite:///./", "")
            absolute_path = BASE_DIR / relative_path
            return f"sqlite:///{absolute_path}"
        return url


settings = Settings()
