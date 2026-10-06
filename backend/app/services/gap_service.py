"""
gap_service.py — Skills Gap Analysis Orchestrator

Flow:
    1. Resolve user skills from DB
    2. Check if stored jobs for this query are fresh enough
       → if stale / missing: auto-scrape and upsert (no duplicates)
    3. Load jobs from DB filtered by the requested date range
    4. Batch-extract market skills from JD text via LLM  (SkillExtractor)
    5. Aggregate market skill frequencies
    6. Compute gap                                        (GapAnalyzer)
    7. Return structured report
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from pymongo.database import Database

from app.ai.gap_analyzer import GapAnalyzer
from app.ai.skill_extractor import SkillExtractor
from app.scrapers.scraper import ScrapeRequest, Scraper
from app.services.job_service import JobService
from app.services.skill_service import SkillService

log = logging.getLogger(__name__)

# ── Tuneable constants ────────────────────────────────────────────────────────

# If the newest job for a query is older than this, trigger a fresh scrape
STALE_THRESHOLD_HOURS: float = 24.0

# Frequency thresholds for gap bucketing
GAP_REQUIRED_THRESHOLD: float = 0.30      # skill in ≥30 % of jobs  → hard gap
GAP_NICE_TO_HAVE_THRESHOLD: float = 0.15  # skill in 15-30 % of jobs → nice-to-have


class GapService:

    @staticmethod
    async def analyze_gap(
        db: Database,
        user_id: str,
        search_term: str,
        location: str,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        force_scrape: bool = False,
        scrape_results_wanted: int = 100,
    ) -> dict:
        """
        Main entry point. Returns a structured gap-analysis report.

        Parameters
        ----------
        db                   : MongoDB connection
        user_id              : whose skills to compare
        search_term          : job-title / keyword used for both scraping & DB query
        location             : city / region (e.g. "Bengaluru, Karnataka")
        from_dt / to_dt      : optional absolute date-range filter on stored jobs.
                               Defaults to all jobs in DB for this query.
        force_scrape         : bypass the staleness check and always re-scrape
        scrape_results_wanted: max jobs to fetch if a scrape is triggered
        """

        # ── Step 1: Resolve user skills ───────────────────────────────────────
        user_skills_objs = SkillService.get_skills(db, user_id=user_id)
        user_skills: list[str] = [s.name for s in user_skills_objs]
        log.info(f"User {user_id} has {len(user_skills)} skills: {user_skills}")

        # ── Step 2: Smart incremental scrape ──────────────────────────────────
        scrape_summary = await GapService._ensure_fresh_jobs(
            db=db,
            search_term=search_term,
            location=location,
            results_wanted=scrape_results_wanted,
            force=force_scrape,
        )
        log.info(f"Scrape summary: {scrape_summary}")

        # ── Step 3: Load jobs from DB (with optional date-range filter) ───────
        query: dict = {
            "title":    {"$regex": search_term, "$options": "i"},
            "location": {"$regex": location,    "$options": "i"},
        }
        if from_dt or to_dt:
            query["created_at"] = {}
            if from_dt:
                query["created_at"]["$gte"] = from_dt
            if to_dt:
                query["created_at"]["$lte"] = to_dt

        jobs = list(db["jobs"].find(query))
        log.info(f"Loaded {len(jobs)} jobs from DB for gap analysis")

        if not jobs:
            return {
                "user_skills": user_skills,
                "jobs_analyzed": 0,
                "market_skills": [],
                "strengths": [],
                "gaps": [],
                "nice_to_have": [],
                "match_score": 0.0,
                "scrape_summary": scrape_summary,
                "message": "No jobs found for this query. Try broadening the search term or location.",
            }

        # ── Step 4: Batch extract market skills via LLM ───────────────────────
        descriptions: list[str] = [
            j["description"] for j in jobs if j.get("description")
        ]
        extractor = SkillExtractor()
        all_extracted: list[list[str]] = await extractor.batch_extract(descriptions)

        # Also fold in any skills already tagged on the job documents themselves
        for i, job in enumerate(jobs):
            if job.get("skills"):
                if i < len(all_extracted):
                    # Merge: union of LLM-extracted + existing tags
                    existing = set(all_extracted[i])
                    all_extracted[i] = list(existing | set(job["skills"]))
                else:
                    all_extracted.append(list(job["skills"]))

        # ── Step 5: Aggregate market skill frequencies ────────────────────────
        flat_skills = [skill for job_skills in all_extracted for skill in job_skills]
        counts = Counter(flat_skills)
        total_jobs = len(jobs)

        market_skills_freq: list[dict] = [
            {"skill": skill, "frequency": round(count / total_jobs, 2)}
            for skill, count in counts.most_common(60)
        ]

        # ── Step 6: Compute gap ───────────────────────────────────────────────
        analyzer = GapAnalyzer()
        gap_result = analyzer.analyze_gap(
            user_skills=user_skills,
            market_skills_freq=market_skills_freq,
            required_threshold=GAP_REQUIRED_THRESHOLD,
            nice_to_have_threshold=GAP_NICE_TO_HAVE_THRESHOLD,
        )

        # ── Step 7: Return structured report ──────────────────────────────────
        return {
            "user_skills": user_skills,
            "jobs_analyzed": total_jobs,
            "market_skills": market_skills_freq,
            "scrape_summary": scrape_summary,
            **gap_result,
        }

    # ── Internal: smart incremental scrape ───────────────────────────────────

    @staticmethod
    async def _ensure_fresh_jobs(
        db: Database,
        search_term: str,
        location: str,
        results_wanted: int,
        force: bool = False,
    ) -> dict:
        """
        Checks staleness of existing jobs for (search_term, location).
        Triggers the scraper only when necessary. Upserts results so no
        duplicates are created.

        Decision logic:
            staleness = None   → no jobs at all             → SCRAPE
            staleness > 24h    → data is stale              → SCRAPE
            staleness ≤ 24h    → data is fresh enough       → SKIP
            force = True       → always scrape regardless   → SCRAPE

        Returns a summary dict describing what happened.
        """
        staleness = JobService.get_staleness_hours(db, search_term, location)

        needs_scrape = (
            force
            or staleness is None                          # no data at all
            or staleness > STALE_THRESHOLD_HOURS          # data is old
        )

        if not needs_scrape:
            log.info(
                f"Jobs are fresh ({staleness:.1f}h old). Skipping scrape."
            )
            return {
                "triggered": False,
                "reason": f"data is {staleness:.1f}h old (threshold={STALE_THRESHOLD_HOURS}h)",
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
            }

        # Determine how far back to scrape:
        # If we have some data, only fetch jobs newer than last scrape.
        # If we have nothing, do a full unrestricted scrape.
        hours_old: Optional[int] = None
        if staleness is not None and not force:
            # Scrape only the delta: jobs newer than the most-recent stored job
            # Add a 1-hour buffer to avoid edge cases at the boundary
            hours_old = int(staleness) + 1

        reason = (
            "force=True" if force
            else "no jobs found" if staleness is None
            else f"data is {staleness:.1f}h old"
        )
        log.info(f"Triggering scrape: {reason}. hours_old={hours_old}")

        scrape_req = ScrapeRequest(
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
        )
        scraper = Scraper(scrape_req)

        # Run synchronously for now (Scraper.run() is blocking / uses requests)
        # TODO: wrap in asyncio.to_thread() when moving to full async stack
        fresh_jobs: list[dict] = scraper.run()
        log.info(f"Scraper returned {len(fresh_jobs)} jobs")

        upsert_summary = JobService.upsert_jobs(db, fresh_jobs)

        return {
            "triggered": True,
            "reason": reason,
            "hours_old_filter": hours_old,
            "scraped": len(fresh_jobs),
            **upsert_summary,   # inserted, updated, skipped
        }

