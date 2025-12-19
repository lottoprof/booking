from fastapi import FastAPI, Request
from fastapi.responses import Response

from app.middleware.auth import auth_middleware
from app.middleware.rate_limit import rate_limit_middleware
from app.middleware.access_policy import access_policy_middleware
from app.middleware.audit import audit_middleware
from app.proxy import proxy_request

app = FastAPI(title="Booking API Gateway")


# ===== Middleware order (ВАЖНО) =====
# 1. audit       → логируем всё
# 2. access      → allow / deny
# 3. rate_limit  → режем трафик
# 4. auth        → определяем client_type

app.middleware("http")(audit_middleware)
app.middleware("http")(access_policy_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(auth_middleware)


# ===== Catch-all proxy =====
@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def gateway_proxy(request: Request, path: str) -> Response:
    return await proxy_request(request)

