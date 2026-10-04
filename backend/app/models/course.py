from pydantic import BaseModel, Field
from typing import Optional

class Course(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    title: str
    provider: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

    model_config = {
        "populate_by_name": True
    }

