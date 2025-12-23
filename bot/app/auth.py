import httpx
import logging

logger = logging.getLogger(__name__)

BACKEND_URL = "http://127.0.0.1:8000"


async def get_user_role(tg_id: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. Получаем user по tg_id
            resp = await client.get(f"{BACKEND_URL}/users/by_tg/{tg_id}")
            logger.info(f"DEBUG [1] users/by_tg status={resp.status_code}")
            
            if resp.status_code != 200:
                return "client"
            
            user = resp.json()
            user_id = user["id"]
            logger.info(f"DEBUG [2] user_id={user_id}")
            
            # 2. Получаем все user_roles
            resp = await client.get(f"{BACKEND_URL}/user_roles/")
            logger.info(f"DEBUG [3] user_roles status={resp.status_code}")
            
            if resp.status_code != 200:
                return "client"
            
            all_roles = resp.json()
            logger.info(f"DEBUG [4] all_roles count={len(all_roles)}")
            
            user_roles = [ur for ur in all_roles if ur["user_id"] == user_id]
            logger.info(f"DEBUG [5] user_roles={user_roles}")
            
            if not user_roles:
                return "client"
            
            # 3. Получаем roles для маппинга id -> name
            resp = await client.get(f"{BACKEND_URL}/roles/")
            logger.info(f"DEBUG [6] roles status={resp.status_code}")
            
            if resp.status_code != 200:
                return "client"
            
            roles_map = {r["id"]: r["name"] for r in resp.json()}
            logger.info(f"DEBUG [7] roles_map={roles_map}")
            
            # 4. Определяем приоритетную роль
            priority = ["admin", "manager", "specialist", "client"]
            user_role_names = [roles_map.get(ur["role_id"], "client") for ur in user_roles]
            logger.info(f"DEBUG [8] user_role_names={user_role_names}")
            
            for role in priority:
                if role in user_role_names:
                    logger.info(f"DEBUG [9] returning role={role}")
                    return role
            
            return "client"
            
    except Exception as e:
        logger.exception(f"get_user_role({tg_id}) failed: {e}")
        return "client"

