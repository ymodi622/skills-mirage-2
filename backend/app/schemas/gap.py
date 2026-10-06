from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class GapAnalysisRequest(BaseModel):
    search_term: str = Field(
        ...,
        description="Target job title or search keyword (e.g. 'Backend Engineer', 'Data Scientist')",
        examples=["Backend Developer"],
    )
    location: Optional[str] = Field(
        None,
        description="City or region for jobs. If omitted, uses the logged-in user's profile location.",
        examples=["Bengaluru, Karnataka"],
    )
    from_dt: Optional[datetime] = Field(
        None,
        description="Optional start date/time filter on stored jobs",
    )
    to_dt: Optional[datetime] = Field(
        None,
        description="Optional end date/time filter on stored jobs",
    )
    force_scrape: bool = Field(
        False,
        description="Force a fresh scrape bypassing the 24-hour staleness check",
    )
    scrape_results_wanted: int = Field(
        50,
        ge=1,
        le=100,
        description="Maximum job listings to scrape if a scrape is triggered (1-100)",
    )


class MarketSkill(BaseModel):
    skill: str
    frequency: float = Field(
        ...,
        description="Relative demand frequency (0.0 to 1.0) across analyzed jobs",
    )


class ScrapeSummary(BaseModel):
    triggered: bool
    reason: Optional[str] = None
    hours_old_filter: Optional[int] = None
    scraped: Optional[int] = 0
    inserted: Optional[int] = 0
    updated: Optional[int] = 0
    skipped: Optional[int] = 0


class GapMetricSummary(BaseModel):
    strengths_count: int
    hard_gaps_count: int
    nice_to_have_count: int
    rare_skills_count: int
    total_market_skills: int
    match_percentage: str


class GapAnalysisResponse(BaseModel):
    user_skills: List[str]
    jobs_analyzed: int
    market_skills: List[MarketSkill]
    strengths: List[str] = Field(
        ...,
        description="Skills present in user profile and highly demanded by market (>=30% freq)",
    )
    gaps: List[str] = Field(
        ...,
        description="Critical skills demanded by market (>=30% freq) that the user lacks",
    )
    nice_to_have: List[str] = Field(
        ...,
        description="Secondary skills demanded by market (15%-30% freq) that the user lacks",
    )
    rare: List[str] = Field(
        default_factory=list,
        description="User skills that have low or zero demand in the analyzed job market (<15% freq)",
    )
    match_score: float = Field(
        ...,
        description="Percentage match score based on user strengths vs required market skills",
    )
    summary: Optional[GapMetricSummary] = None
    scrape_summary: Optional[ScrapeSummary] = None
    message: Optional[str] = None
