from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from pymongo.database import Database

from app.core.database import get_db
from app.models.user import User
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate, TagsPayload
from app.services.auth_service import AuthService
from app.services.course_service import CourseService

router = APIRouter()


# ── CREATE ────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a course listing",
)
def create_course(
    payload: CourseCreate,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return CourseService.create_course(db=db, payload=payload)


# ── LIST / SEARCH ─────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=List[CourseResponse],
    summary="List / search course listings",
    description=(
        "Returns a paginated, newest-first list of courses. "
        "All filters are optional and case-insensitive."
    ),
)
def list_courses(
    title: Optional[str] = Query(None, description="Partial title match"),
    provider: Optional[str] = Query(None, description="Filter by provider (e.g. nptel, coursera)"),
    level: Optional[str] = Query(None, description="Partial level match (e.g. beginner)"),
    language: Optional[str] = Query(None, description="Filter by language"),
    tag: Optional[str] = Query(None, description="Filter by a single tag"),
    is_free: Optional[bool] = Query(None, description="Filter free / paid courses"),
    certificate: Optional[bool] = Query(None, description="Filter courses offering certificates"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return CourseService.list_courses(
        db=db,
        title=title,
        provider=provider,
        level=level,
        language=language,
        tag=tag,
        is_free=is_free,
        certificate=certificate,
        skip=skip,
        limit=limit,
    )


# ── READ (single) ─────────────────────────────────────────────────────────────

@router.get(
    "/{course_id}",
    response_model=CourseResponse,
    summary="Get a course by ID",
)
def get_course(
    course_id: str,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return CourseService.get_course(db=db, course_id=course_id)


# ── UPDATE (partial patch) ────────────────────────────────────────────────────

@router.patch(
    "/{course_id}",
    response_model=CourseResponse,
    summary="Partially update a course listing",
    description="Only the fields you supply will be changed.",
)
def update_course(
    course_id: str,
    payload: CourseUpdate,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    update_data = payload.model_dump(exclude_unset=True)
    return CourseService.update_course(db=db, course_id=course_id, payload=update_data)


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete(
    "/{course_id}",
    summary="Delete a course listing",
    status_code=status.HTTP_200_OK,
)
def delete_course(
    course_id: str,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return CourseService.delete_course(db=db, course_id=course_id)


# ── TAG helpers ───────────────────────────────────────────────────────────────

@router.post(
    "/{course_id}/tags",
    response_model=CourseResponse,
    summary="Add tags to a course",
    description="Uses MongoDB $addToSet – duplicates are ignored automatically.",
)
def add_tags(
    course_id: str,
    payload: TagsPayload,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return CourseService.add_tags(db=db, course_id=course_id, tags=payload.tags)


@router.delete(
    "/{course_id}/tags",
    response_model=CourseResponse,
    summary="Remove tags from a course",
)
def remove_tags(
    course_id: str,
    payload: TagsPayload,
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return CourseService.remove_tags(db=db, course_id=course_id, tags=payload.tags)


# ── SCRAPE & STORE ────────────────────────────────────────────────────────────

@router.post(
    "/scrape",
    summary="Scrape courses and persist to DB",
    status_code=status.HTTP_200_OK,
    description=(
        "Triggers the CourseScraper pipeline for the given keyword, "
        "upserts results into MongoDB, and returns an ingestion summary."
    ),
)
def scrape_courses(
    keyword: str = Query(..., description="Search keyword for the scraper"),
    sources: Optional[List[str]] = Query(
        None,
        description="Comma-separated list of sources (nptel, swayam, mit_ocw, edx, coursera, udemy). "
                    "Defaults to all sources.",
    ),
    max_results: int = Query(30, ge=1, le=200, description="Max courses to fetch per source"),
    db: Database = Depends(get_db),
    _current_user: User = Depends(AuthService.get_current_user),
):
    return CourseService.scrape_and_store(
        db=db,
        keyword=keyword,
        sources=sources,
        max_results=max_results,
    )
