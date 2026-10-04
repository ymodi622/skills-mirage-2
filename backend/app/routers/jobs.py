from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from pymongo.database import Database

from app.core.database import get_db
from app.models.user import User
from app.schemas.job import JobCreate, JobResponse, JobUpdate, SkillsPayload
from app.services.auth_service import AuthService
from app.services.job_service import JobService

router = APIRouter()


# ── CREATE ────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job listing",
)
def create_job(
    payload: JobCreate,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return JobService.create_job(db=db, payload=payload)


# ── LIST / SEARCH ─────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=List[JobResponse],
    summary="List / search job listings",
    description=(
        "Returns a paginated, newest-first list of jobs. "
        "All filters are optional and case-insensitive."
    ),
)
def list_jobs(
    title: Optional[str] = Query(None, description="Partial title match"),
    company: Optional[str] = Query(None, description="Partial company name match"),
    location: Optional[str] = Query(None, description="Partial location match"),
    source: Optional[str] = Query(None, description="Filter by source platform"),
    skill: Optional[str] = Query(None, description="Filter by a single required skill"),
    experience_min: Optional[int] = Query(None, ge=0, description="Minimum years of experience"),
    experience_max: Optional[int] = Query(None, ge=0, description="Maximum years of experience"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return JobService.list_jobs(
        db=db,
        title=title,
        company=company,
        location=location,
        source=source,
        skill=skill,
        experience_min=experience_min,
        experience_max=experience_max,
        skip=skip,
        limit=limit,
    )


# ── READ (single) ─────────────────────────────────────────────────────────────

@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get a job by ID",
)
def get_job(
    job_id: str,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return JobService.get_job(db=db, job_id=job_id)


# ── UPDATE (partial patch) ────────────────────────────────────────────────────

@router.patch(
    "/{job_id}",
    response_model=JobResponse,
    summary="Partially update a job listing",
    description="Only the fields you supply will be changed.",
)
def update_job(
    job_id: str,
    payload: JobUpdate,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    # Exclude unset so only explicitly provided fields are patched
    update_data = payload.model_dump(exclude_unset=True)
    return JobService.update_job(db=db, job_id=job_id, payload=update_data)


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete(
    "/{job_id}",
    summary="Delete a job listing",
    status_code=status.HTTP_200_OK,
)
def delete_job(
    job_id: str,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return JobService.delete_job(db=db, job_id=job_id)


# ── SKILLS helpers ────────────────────────────────────────────────────────────

@router.post(
    "/{job_id}/skills",
    response_model=JobResponse,
    summary="Add skill tags to a job",
    description="Uses MongoDB $addToSet – duplicates are ignored automatically.",
)
def add_skills(
    job_id: str,
    payload: SkillsPayload,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return JobService.add_skills(db=db, job_id=job_id, skills=payload.skills)


@router.delete(
    "/{job_id}/skills",
    response_model=JobResponse,
    summary="Remove skill tags from a job",
)
def remove_skills(
    job_id: str,
    payload: SkillsPayload,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return JobService.remove_skills(db=db, job_id=job_id, skills=payload.skills)
