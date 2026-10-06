from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field


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


class SkillItem(BaseModel):
    name: str
    category: cat_enum = cat_enum.tech


class BulkSkillsPayload(BaseModel):
    skills: List[Union[SkillItem, str]] = Field(
        ...,
        description="List of skill objects or string skill names",
        examples=[
            [
                {"name": "Python", "category": "tech"},
                {"name": "FastAPI", "category": "tech"},
                {"name": "Communication", "category": "non-tech"},
            ]
        ],
    )


class BulkSkillsResponse(BaseModel):
    total_submitted: int
    inserted: int
    existing: int
    message: str
