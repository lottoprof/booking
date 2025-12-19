# пишет: method / path / status; client_type; IP / UA; время обработки
# НЕ блокирует запрос; НЕ пишет в БД

import time
from fastapi import Request
import json
import logging

logger = logging.getLogger("gateway.audit")
logging.basicConfig(level=logging.INFO)


async def audit_middleware(request: Request, call_next):
    start_ts = time.time()

    response = await call_next(request)

    duration_ms = int((time.time() - start_ts) * 1000)

    record = {
        "ts": int(start_ts),
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "client_type": getattr(request.state, "client_type", "unknown"),
        "ip": request.headers.get("X-Real-IP") or request.client.host,
        "ua": request.headers.get("User-Agent", ""),
        "duration_ms": duration_ms
    }

    logger.info(json.dumps(record, ensure_ascii=False))

    return response

