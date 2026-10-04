from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timezone
from typing import Optional, List


# ── Embedded sub-documents ──────────────────────────────────────────────────

class CurrentJob(BaseModel):
    """Embedded document for a user's current employment."""
    title: str
    position: str
    description: Optional[str] = None


# ── Main User document model (maps 1-to-1 to MongoDB) ──────────────────────

class User(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    email: EmailStr

    # credentials (password is always hashed before storage)
    password: str

    # profile
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    is_student: bool = False

    # Only present when is_student is False
    current_job: Optional[CurrentJob] = None

    interests: List[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }
