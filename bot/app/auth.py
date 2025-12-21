import httpx
import logging

logger = logging.getLogger(__name__)

BACKEND_URL = "http://127.0.0.1:8000"


async def get_user_role(tg_id: int) -> str:
    """
    Возвращает главную роль пользователя.
    Приоритет: admin > manager > specialist > client
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. Получаем user по tg_id
            resp = await client.get(f"{BACKEND_URL}/users/by_tg/{tg_id}")
            if resp.status_code != 200:
                return "client"
            
            user = resp.json()
            user_id = user["id"]
            
            # 2. Получаем все user_roles
            resp = await client.get(f"{BACKEND_URL}/user_roles/")
            if resp.status_code != 200:
                return "client"
            
            user_roles = [ur for ur in resp.json() if ur["user_id"] == user_id]
            if not user_roles:
                return "client"
            
            # 3. Получаем roles для маппинга id -> name
            resp = await client.get(f"{BACKEND_URL}/roles/")
            if resp.status_code != 200:
                return "client"
            
            roles_map = {r["id"]: r["name"] for r in resp.json()}
            
            # 4. Определяем приоритетную роль
            priority = ["admin", "manager", "specialist", "client"]
            user_role_names = [roles_map.get(ur["role_id"], "client") for ur in user_roles]
            
            for role in priority:
                if role in user_role_names:
                    return role
            
            return "client"
            
    except Exception as e:
        logger.warning(f"get_user_role({tg_id}) failed: {e}")
        return "client"
