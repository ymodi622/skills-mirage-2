"""
course_scraper.py — Unified Course Metadata Scraper (Orchestrator)

Usage (dependency injection pattern — mirrors scraper.py):

    request = CourseScraperRequest(
        keyword="machine learning",
        max_results=50,
        sources=["nptel", "swayam", "mit_ocw", "edx", "coursera", "udemy"],
    )
    scraper = CourseScraper(request)
    courses: list[dict] = scraper.run()

Output JSON schema (per course):
    {
        "title":         str | None
        "provider":      str          — "nptel" | "swayam" | "mit_ocw" | "edx" | "coursera" | "udemy"
        "url":           str | None   — canonical course page URL (no download links)
        "description":   str | None   — short summary only
        "thumbnail_url": str | None   — cover image URL
        "instructor":    str | None   — primary instructor / institution name
        "duration":      str | None   — e.g. "12 weeks", "6h 30m"
        "level":         str | None   — "Beginner" / "Intermediate" / "Advanced"
        "language":      str | None   — e.g. "English", "Hindi"
        "tags":          list[str]    — topic / skill tags
        "rating":        float | None — 0–5 star rating
        "num_reviews":   int | None   — number of ratings
        "is_free":       bool | None  — free to enroll?
        "certificate":   bool | None  — certificate offered?
        "scraped_at":    str          — ISO-8601 UTC timestamp
        "source_id":     str | None   — platform-native course identifier
    }

Rules enforced by this module:
    ✅ Only metadata + links extracted
    ❌ No videos / PDFs / transcripts / lecture content downloaded
"""

from __future__ import annotations

import json
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.scrapers.courses.base import BaseCourseSource
from app.scrapers.courses.utils import deduplicate_courses, safe_str
from app.scrapers.courses.sources.nptel import NPTELSource, SWAYAMSource
from app.scrapers.courses.sources.mit_ocw import MITOCWSource
from app.scrapers.courses.sources.edx import EdXSource
from app.scrapers.courses.sources.coursera import CourseraSource
from app.scrapers.courses.sources.udemy import UdemySource

log = logging.getLogger(__name__)

# All supported source identifiers
SourceName = Literal["nptel", "swayam", "mit_ocw", "edx", "coursera", "udemy"]

_ALL_SOURCES: list[SourceName] = ["nptel", "swayam", "mit_ocw", "edx", "coursera", "udemy"]


# ─── Input model (dependency injection) ──────────────────────────────────────

class CourseScraperRequest(BaseModel):
    """
    Pydantic model for all course-scrape parameters — injected by the caller.
    Nothing is hardcoded in CourseScraper; everything flows from here.

    Can be used directly as a FastAPI request body:
        @router.post("/courses/scrape")
        def scrape_courses(req: CourseScraperRequest): ...

    Attributes:
        keyword     : search term (e.g. "data science", "web development")
        max_results : upper bound on total courses returned across all sources
        sources     : which platforms to query; defaults to all supported ones
        language    : preferred language filter hint passed to sources (best-effort)
        timeout     : per-source timeout in seconds; sources respect this individually
    """

    keyword: str
    max_results: int = Field(default=30, ge=1, le=500)
    sources: list[SourceName] = Field(default_factory=lambda: list(_ALL_SOURCES))
    language: Optional[str] = None    # e.g. "English", "Hindi" — passed to sources
    timeout: int = Field(default=20, ge=5, le=120)

    @field_validator("keyword")
    @classmethod
    def keyword_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("keyword must not be blank")
        return v.strip()

    @field_validator("sources")
    @classmethod
    def sources_must_not_be_empty(cls, v: list[SourceName]) -> list[SourceName]:
        if not v:
            raise ValueError("at least one source must be specified")
        return v


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class CourseScraper:
    """
    Unified scraper that fetches course metadata from multiple open platforms
    and returns a deduplicated, normalized list of dicts (JSON-serializable).

    Designed for dependency injection: all configuration lives in
    CourseScraperRequest.  CourseScraper itself has no hardcoded values.

    Platform availability notes:
        nptel    ✅ Free Indian MOOC platform — good API coverage
        swayam   ✅ GOI platform — delegates many courses to NPTEL
        mit_ocw  ✅ Public JSON API — always free, no certificate
        edx      ⚠️ Hidden API may change; HTML fallback available
        coursera ✅ Public catalog API — reliable, rich metadata
        udemy    ⚠️ API may 403 from India without UA tricks; HTML fallback
    """

    # Maps source name → class (lazy-instantiated per run)
    _SOURCE_MAP: dict[SourceName, type[BaseCourseSource]] = {
        "nptel":    NPTELSource,
        "swayam":   SWAYAMSource,
        "mit_ocw":  MITOCWSource,
        "edx":      EdXSource,
        "coursera": CourseraSource,
        "udemy":    UdemySource,
    }

    def __init__(self, request: CourseScraperRequest) -> None:
        self.request = request

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self) -> list[dict]:
        """
        Orchestrates the full course extraction pipeline:
          1. Query each configured source for the keyword
          2. Merge raw results from all sources
          3. Deduplicate by URL (or title as fallback)
          4. Normalize field values
          5. Cap at max_results

        Returns:
            List of normalized, JSON-serializable course dicts.
        """
        log.info(
            "Scraping courses for keyword='%s' from sources=%s (limit=%d)",
            self.request.keyword,
            self.request.sources,
            self.request.max_results,
        )

        raw_courses = self._fetch_all()

        if not raw_courses:
            log.warning("No courses returned from any source.")
            return []

        unique_courses = deduplicate_courses(raw_courses)
        normalized     = self._normalize_all(unique_courses)
        result         = normalized[:self.request.max_results]

        # Summary log
        by_source: dict[str, int] = {}
        for c in result:
            src = c.get("provider", "unknown")
            by_source[src] = by_source.get(src, 0) + 1

        log.info(
            "Done: %d courses total | by source: %s",
            len(result),
            by_source,
        )
        return result

    # ── Step 1: Fetch from all sources ────────────────────────────────────────

    def _fetch_all(self) -> list[dict]:
        """
        Calls each enabled source's fetch() method sequentially and collects
        all raw results.  Each source runs independently; a failure in one
        does not affect the others (sources catch their own exceptions).
        """
        all_results: list[dict] = []

        # Distribute max_results across sources evenly
        per_source = max(10, self.request.max_results // len(self.request.sources))

        for source_name in self.request.sources:
            source_cls = self._SOURCE_MAP.get(source_name)
            if not source_cls:
                log.warning("Unknown source '%s'; skipping.", source_name)
                continue

            try:
                source: BaseCourseSource = source_cls()
                results = source.fetch(
                    keyword=self.request.keyword,
                    max_results=per_source,
                )
                log.debug("Source '%s' returned %d course(s).", source_name, len(results))
                all_results.extend(results)
            except Exception as exc:
                # Belt-and-suspenders: sources should not raise, but just in case
                log.error("Unexpected error from source '%s': %s", source_name, exc)

        return all_results

    # ── Step 2: Normalize ─────────────────────────────────────────────────────

    def _normalize_all(self, courses: list[dict]) -> list[dict]:
        """Apply final normalization to every course dict."""
        return [self._normalize_one(c) for c in courses]

    def _normalize_one(self, course: dict) -> dict:
        """
        Ensures every course dict conforms to the output schema:
          - All expected keys are present (defaulting to None / [])
          - Strings are stripped and capped
          - tags list contains only non-empty strings
          - rating is clamped to [0, 5]
        """
        title = safe_str(course.get("title"), max_len=200)
        if not title:
            title = "(Untitled)"

        tags = [
            safe_str(t, max_len=50)
            for t in (course.get("tags") or [])
            if t
        ]
        tags = [t for t in tags if t]

        rating = course.get("rating")
        if rating is not None:
            try:
                rating = max(0.0, min(5.0, float(rating)))
            except (TypeError, ValueError):
                rating = None

        return {
            "title":         title,
            "provider":      safe_str(course.get("provider")) or "unknown",
            "url":           safe_str(course.get("url")),
            "description":   safe_str(course.get("description"), max_len=1000),
            "thumbnail_url": safe_str(course.get("thumbnail_url")),
            "instructor":    safe_str(course.get("instructor"), max_len=200),
            "duration":      safe_str(course.get("duration"), max_len=50),
            "level":         safe_str(course.get("level"), max_len=50),
            "language":      safe_str(course.get("language"), max_len=50) or "English",
            "tags":          tags,
            "rating":        rating,
            "num_reviews":   course.get("num_reviews") if isinstance(course.get("num_reviews"), int) else None,
            "is_free":       course.get("is_free"),
            "certificate":   course.get("certificate"),
            "scraped_at":    safe_str(course.get("scraped_at")),
            "source_id":     safe_str(course.get("source_id")),
        }


# ─── CLI / standalone test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    keyword = sys.argv[1] if len(sys.argv) > 1 else "machine learning"
    sources_arg = sys.argv[2].split(",") if len(sys.argv) > 2 else list(_ALL_SOURCES)

    request = CourseScraperRequest(
        keyword=keyword,
        max_results=50,
        sources=sources_arg,
    )

    scraper = CourseScraper(request)
    courses = scraper.run()

    print(f"\n{'='*60}")
    print(f"Keyword    : {keyword}")
    print(f"Sources    : {sources_arg}")
    print(f"Total found: {len(courses)}")
    print(f"{'='*60}\n")

    # Print first 3 as pretty JSON
    print(json.dumps(courses[:3], indent=2, default=str))

    # Save all to JSON
    out_file = "courses.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, default=str, ensure_ascii=False)
    print(f"\nSaved {len(courses)} courses → {out_file}")
