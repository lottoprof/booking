# матч path + method
# проверяет client_type
# default = deny
# wildcard (*) поддержан
# готов к hot-reload (policy.reload())

import json
import fnmatch
from pathlib import Path
from fastapi import Request, HTTPException

POLICY_PATH = Path(__file__).resolve().parent.parent / "policy" / "policy.json"

class AccessPolicy:
    def __init__(self):
        self._load_policy()

    def _load_policy(self):
        with open(POLICY_PATH, "r", encoding="utf-8") as f:
            self.policy = json.load(f)

        self.rules = self.policy.get("access_rules", [])
        self.default_action = self.policy.get("meta", {}).get("default_action", "deny")

    def reload(self):
        self._load_policy()

    def is_allowed(self, path: str, method: str, client_type: str) -> bool:
        for rule in self.rules:
            if method not in rule["methods"]:
                continue

            for p in rule["path"]:
                if fnmatch.fnmatch(path, p):
                    return client_type in rule["allow"]

        return self.default_action == "allow"


policy = AccessPolicy()

async def access_policy_middleware(request: Request, call_next):
    path = request.url.path

    # Инфраструктурные endpoints — без policy check
    if path in ("/tg/webhook", "/oauth/google/callback"):
        return await call_next(request)

    client_type = request.state.client_type
    method = request.method

    if not policy.is_allowed(path, method, client_type):
        raise HTTPException(status_code=403, detail="Access denied")

    return await call_next(request)
