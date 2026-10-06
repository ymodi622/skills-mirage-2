from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


# ── Shared / embedded schemas ────────────────────────────────────────────────

class CurrentJobSchema(BaseModel):
    title: str
    position: str
    description: Optional[str] = None


# ── Auth schemas (keep here for backwards compat) ────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    message: str
    user_id: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str


# ── Profile CRUD schemas ─────────────────────────────────────────────────────

class UserProfileCreate(BaseModel):
    """
    Request body for POST /users/profile.
    When is_student=True, current_job must be omitted / None.
    """
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    is_student: bool = False
    current_job: Optional[CurrentJobSchema] = None
    interests: Optional[List[str]] = None
    skills: Optional[List[str]] = None


class UserProfileUpdate(BaseModel):
    """
    Request body for PATCH /users/profile – every field is optional.
    Pass only the fields you want to change.
    """
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    is_student: Optional[bool] = None
    current_job: Optional[CurrentJobSchema] = None
    interests: Optional[List[str]] = None
    skills: Optional[List[str]] = None


class UserSkillsPayload(BaseModel):
    skills: List[str] = Field(
        ...,
        description="List of skill names (e.g. ['Python', 'Docker']) or skill ObjectIds",
        examples=[["Python", "FastAPI", "MongoDB"]],
    )


class UserProfileResponse(BaseModel):
    """Public-facing user profile (never exposes password)."""
    id: Optional[str] = Field(default=None, alias="_id")
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    is_student: bool = False
    current_job: Optional[CurrentJobSchema] = None
    interests: List[str] = []
    skills: List[str] = []

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }