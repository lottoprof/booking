import os
from urllib.parse import urlparse
from dotenv import load_dotenv

# Загружаем .env (как в backend)
load_dotenv()

# ===== Redis =====

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1")
parsed = urlparse(REDIS_URL)

REDIS_HOST = parsed.hostname or "127.0.0.1"
REDIS_PORT = parsed.port or 6379
REDIS_DB = int(parsed.path.lstrip("/") or 0)
REDIS_PASSWORD = parsed.password

REDIS_RATE_LIMIT_PREFIX = "rl"
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "2.0"))

# ===== Domain API =====

DOMAIN_API_URL = os.getenv(
    "DOMAIN_API_URL",
    "http://127.0.0.1:8000"
)

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
