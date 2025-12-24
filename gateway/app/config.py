# gateway/app/config.py

import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# ===== Redis =====

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL not set in .env")

parsed = urlparse(REDIS_URL)

REDIS_HOST = parsed.hostname
REDIS_PORT = parsed.port or 6379
REDIS_DB = int(parsed.path.lstrip("/") or 0)
REDIS_PASSWORD = parsed.password

REDIS_RATE_LIMIT_PREFIX = "rl"
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "2.0"))

# ===== Domain API (Backend) =====

DOMAIN_API_URL = os.getenv("DOMAIN_API_URL")
if not DOMAIN_API_URL:
    raise RuntimeError("DOMAIN_API_URL not set in .env")

# ===== Gateway =====

GATEWAY_HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8080"))

# ===== Telegram =====

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

