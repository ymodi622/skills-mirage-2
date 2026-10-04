from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional, List


class Job(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    title: str
    company: str
    location: str
    description: str

    experience_min: Optional[int] = None
    experience_max: Optional[int] = None

    skills: List[str] = Field(default_factory=list)

    source: str
    source_url: Optional[str] = None

    posted_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }
