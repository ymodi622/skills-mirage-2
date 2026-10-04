from fastapi import APIRouter, Depends, Query, status
from app.models.skill import Skill
from app.services.skill_service import SkillService
from app.core.database import get_db
from pymongo.database import Database
from typing import List, Optional

router = APIRouter()

@router.get("/",response_model=List[Skill])
def get_skills(category : Optional[str] = None,user_id: Optional[str] = None, db : Database = Depends(get_db)):
    return SkillService.get_skills(category=category, user_id=user_id, db=db)

@router.post('/', status_code=status.HTTP_201_CREATED)
def create_skill(skill:Skill, db:Database = Depends(get_db)):
    return SkillService.create_skill(skill=skill, db = db)