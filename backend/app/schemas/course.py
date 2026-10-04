from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    title: str
    provider: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    instructor: Optional[str] = None
    duration: Optional[str] = None
    level: Optional[str] = None
    language: Optional[str] = None
    tags: List[str] = []
    rating: Optional[float] = None
    num_reviews: Optional[int] = None
    is_free: Optional[bool] = None
    certificate: Optional[bool] = None
    source_id: Optional[str] = None
    scraped_at: Optional[str] = None


class CourseUpdate(BaseModel):
    """Partial update – all fields optional."""
    title: Optional[str] = None
    provider: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    instructor: Optional[str] = None
    duration: Optional[str] = None
    level: Optional[str] = None
    language: Optional[str] = None
    tags: Optional[List[str]] = None
    rating: Optional[float] = None
    num_reviews: Optional[int] = None
    is_free: Optional[bool] = None
    certificate: Optional[bool] = None


class TagsPayload(BaseModel):
    """Payload for adding or removing tags on a course."""
    tags: List[str]


class CourseResponse(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    title: str
    provider: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    instructor: Optional[str] = None
    duration: Optional[str] = None
    level: Optional[str] = None
    language: Optional[str] = None
    tags: List[str] = []
    rating: Optional[float] = None
    num_reviews: Optional[int] = None
    is_free: Optional[bool] = None
    certificate: Optional[bool] = None
    source_id: Optional[str] = None
    scraped_at: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }
