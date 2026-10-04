from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from pymongo.database import Database

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.auth_service import AuthService
from app.services.user_service import UserService

router = APIRouter()


# ── LIST all users (admin / discovery) ───────────────────────────────────────

@router.get(
    "/",
    response_model=List[UserProfileResponse],
    summary="List users",
    description=(
        "Returns a paginated list of users. Supports optional filters by "
        "state, city, student status, and interest."
    ),
)
def list_users(
    state: Optional[str] = Query(None, description="Filter by state (case-insensitive)"),
    city: Optional[str] = Query(None, description="Filter by city (case-insensitive)"),
    is_student: Optional[bool] = Query(None, description="Filter students vs professionals"),
    interest: Optional[str] = Query(None, description="Filter by a single interest tag"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return UserService.list_users(
        db=db,
        state=state,
        city=city,
        is_student=is_student,
        interest=interest,
        skip=skip,
        limit=limit,
    )


# ── GET current logged-in user's profile ─────────────────────────────────────

@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get my profile",
)
def get_me(
    current_user: User = Depends(AuthService.get_current_user),
    db: Database = Depends(get_db),
):
    return UserService.get_user(db=db, user_id=current_user.id)


# ── CREATE / initialise profile for current user ──────────────────────────────

@router.post(
    "/me/profile",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create / initialise my profile",
    description=(
        "Set profile fields (location, student flag, current job, interests). "
        "When `is_student=true` do NOT supply `current_job`."
    ),
)
def create_my_profile(
    payload: UserProfileCreate,
    current_user: User = Depends(AuthService.get_current_user),
    db: Database = Depends(get_db),
):
    return UserService.create_profile(db=db, user_id=current_user.id, payload=payload)


# ── PATCH / partial-update current user's profile ────────────────────────────

@router.patch(
    "/me",
    response_model=UserProfileResponse,
    summary="Update my profile",
    description="Partial update – only the fields you provide will be changed.",
)
def update_me(
    payload: UserProfileUpdate,
    current_user: User = Depends(AuthService.get_current_user),
    db: Database = Depends(get_db),
):
    return UserService.update_user(db=db, user_id=current_user.id, payload=payload)


# ── DELETE current user's account ─────────────────────────────────────────────

@router.delete(
    "/me",
    summary="Delete my account",
    status_code=status.HTTP_200_OK,
)
def delete_me(
    current_user: User = Depends(AuthService.get_current_user),
    db: Database = Depends(get_db),
):
    return UserService.delete_user(db=db, user_id=current_user.id)


# ── Admin / scoped: GET any user by ID ───────────────────────────────────────

@router.get(
    "/{user_id}",
    response_model=UserProfileResponse,
    summary="Get user by ID",
)
def get_user(
    user_id: str,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return UserService.get_user(db=db, user_id=user_id)


# ── Admin / scoped: PATCH any user by ID ─────────────────────────────────────

@router.patch(
    "/{user_id}",
    response_model=UserProfileResponse,
    summary="Update user by ID",
)
def update_user(
    user_id: str,
    payload: UserProfileUpdate,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return UserService.update_user(db=db, user_id=user_id, payload=payload)


# ── Admin / scoped: DELETE any user by ID ────────────────────────────────────

@router.delete(
    "/{user_id}",
    summary="Delete user by ID",
    status_code=status.HTTP_200_OK,
)
def delete_user(
    user_id: str,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return UserService.delete_user(db=db, user_id=user_id)
