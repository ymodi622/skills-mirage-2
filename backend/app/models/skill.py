from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
class cat_enum(str, Enum):
    tech = "tech"
    non_tech = "non-tech"
class Skill(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    category: cat_enum = cat_enum.tech

    model_config = {
        "populate_by_name": True
    }

