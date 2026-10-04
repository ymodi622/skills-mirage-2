from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


class JobCreate(BaseModel):
    title: str
    company: str
    location: str
    description: str

    experience_min: Optional[int] = None
    experience_max: Optional[int] = None

    source: str
    source_url: Optional[str] = None

    posted_at: Optional[datetime] = None


class JobUpdate(BaseModel):
    """Partial update – all fields optional."""
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    posted_at: Optional[datetime] = None


class SkillsPayload(BaseModel):
    """Payload for adding or removing skill tags on a job."""
    skills: List[str]


class JobResponse(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    title: str
    company: str
    location: str
    description: str
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    skills: List[str] = []
    source: str
    source_url: Optional[str] = None
    posted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }