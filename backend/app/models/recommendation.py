from pydantic import BaseModel, Field
from typing import Optional

class Recommendation(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    item_type: str
    item_id: str
    score: float

    model_config = {
        "populate_by_name": True
    }

