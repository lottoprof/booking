# backend/app/schemas/roles.py

from pydantic import BaseModel


class RoleRead(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}

