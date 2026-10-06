from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.core.database import get_db
from app.models.user import User
from app.schemas.gap import GapAnalysisRequest, GapAnalysisResponse
from app.services.auth_service import AuthService
from app.services.gap_service import GapService

router = APIRouter()


@router.post(
    "/analyze",
    response_model=GapAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run End-to-End Skills Gap Analysis",
    description=(
        "Analyzes the gap between the authenticated user's current profile skills "
        "and market job postings. Automatically manages job freshness via smart scraping, "
        "extracts technical skills from job descriptions via LLM, and calculates skill strengths, "
        "critical gaps, nice-to-haves, and an overall match score."
    ),
)
async def analyze_skills_gap(
    payload: GapAnalysisRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user),
):
    # Resolve location: prioritize request payload, fallback to user profile, then default
    location = payload.location
    if not location or not location.strip():
        if current_user.city and current_user.state:
            location = f"{current_user.city}, {current_user.state}"
        elif current_user.city:
            location = current_user.city
        elif current_user.state:
            location = current_user.state
        else:
            location = "India"

    try:
        result = await GapService.analyze_gap(
            db=db,
            user_id=current_user.id,
            search_term=payload.search_term,
            location=location,
            from_dt=payload.from_dt,
            to_dt=payload.to_dt,
            force_scrape=payload.force_scrape,
            scrape_results_wanted=payload.scrape_results_wanted,
        )
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gap analysis failed: {str(exc)}",
        )
