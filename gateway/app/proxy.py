#  проксирует любой метод
#  проксирует любой путь
#  передаёт body / headers


import httpx
from fastapi import Request, Response
from app.config import DOMAIN_API_URL


async def proxy_request(request: Request) -> Response:
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"{DOMAIN_API_URL}{request.url.path}"

        if request.url.query:
            url += f"?{request.url.query}"

        body = await request.body()

        # --- headers ---
        headers = dict(request.headers)
        headers.pop("host", None)

        # ===== прокидываем ТОЛЬКО нормализованную TG-identity =====
        identity = getattr(request.state, "identity", None)
        if identity:
            if identity.get("tg_id") is not None:
                headers["X-TG-ID"] = str(identity["tg_id"])
            if identity.get("username"):
                headers["X-TG-USERNAME"] = identity["username"]
            if identity.get("auth_date"):
                headers["X-TG-AUTH-DATE"] = str(identity["auth_date"])

        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body
        )

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )

