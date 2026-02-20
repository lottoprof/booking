# пишет: method / path / status; client_type; IP / UA; время обработки
# НЕ блокирует запрос; НЕ пишет в БД

import json
import logging
import time

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

logger = logging.getLogger("gateway.audit")
logging.basicConfig(level=logging.INFO)


async def audit_middleware(request: Request, call_next):
    start_ts = time.time()

    try:
        response = await call_next(request)
        status = response.status_code
    except HTTPException as exc:
        status = exc.status_code
        response = JSONResponse(
            status_code=status,
            content={"detail": exc.detail},
        )

    duration_ms = int((time.time() - start_ts) * 1000)

    record = {
        "ts": int(start_ts),
        "method": request.method,
        "path": request.url.path,
        "status": status,
        "client_type": getattr(request.state, "client_type", "unknown"),
        "ip": request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown"),
        "ua": request.headers.get("User-Agent", ""),
        "duration_ms": duration_ms
    }

    logger.info(json.dumps(record, ensure_ascii=False))

    return response

