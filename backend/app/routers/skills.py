from typing import List, Optional, Union
from fastapi import APIRouter, Depends, Query, status
from pymongo.database import Database

from app.core.database import get_db
from app.models.skill import (
    Skill,
    SkillItem,
    BulkSkillsPayload,
    BulkSkillsResponse,
)
from app.services.skill_service import SkillService

router = APIRouter()


@router.get(
    "/",
    response_model=List[Skill],
    summary="Get skills list",
    description="Fetch all skills, optionally filtered by category or user_id.",
)
def get_skills(
    category: Optional[str] = None,
    user_id: Optional[str] = None,
    db: Database = Depends(get_db),
):
    return SkillService.get_skills(category=category, user_id=user_id, db=db)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create a single skill",
)
def create_skill(
    skill: Skill,
    db: Database = Depends(get_db),
):
    return SkillService.create_skill(skill=skill, db=db)


@router.post(
    "/batch",
    response_model=BulkSkillsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add multiple skills at once",
    description=(
        "Bulk insert skills into the master catalog. Accepts either a wrapper "
        "{'skills': [...]} or a direct JSON array of skill items or skill name strings. "
        "Automatically deduplicates and preserves existing skills."
    ),
)
def create_skills_batch(
    payload: Union[BulkSkillsPayload, List[Union[SkillItem, str]]],
    db: Database = Depends(get_db),
):
    items = payload.skills if isinstance(payload, BulkSkillsPayload) else payload
    return SkillService.create_skills_batch(db=db, items=items)