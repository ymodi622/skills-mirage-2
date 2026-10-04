"""
base.py — Abstract contract for all course scraper sources.

Every platform-specific scraper MUST inherit BaseCourseSource and
implement the `fetch` method.  The orchestrator (CourseScraper) works
exclusively through this interface, so adding a new platform requires
only:
  1. Create a new file in sources/
  2. Subclass BaseCourseSource
  3. Register the key in CourseScraper._SOURCE_MAP
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseCourseSource(ABC):
    """
    Abstract base class for all course-metadata scrapers.

    Subclasses must implement `fetch` which returns a list of flat,
    JSON-serializable dicts conforming to the course metadata schema:

        {
            "title":         str            – course title (required)
            "provider":      str            – platform name, e.g. "nptel"
            "url":           str | None     – canonical course page URL
            "description":   str | None     – short summary (NO lecture text)
            "thumbnail_url": str | None     – cover image URL
            "instructor":    str | None     – primary instructor name(s)
            "duration":      str | None     – human-readable, e.g. "12 weeks"
            "level":         str | None     – "Beginner" / "Intermediate" / "Advanced"
            "language":      str | None     – "English", "Hindi", etc.
            "tags":          list[str]      – topic/skill tags
            "rating":        float | None   – 0–5 star rating
            "num_reviews":   int | None     – number of ratings/reviews
            "is_free":       bool | None    – free to access?
            "certificate":   bool | None    – certificate offered?
            "scraped_at":    str            – ISO-8601 UTC timestamp
            "source_id":     str | None     – platform-native course identifier
        }

    Rules:
        - NEVER download videos, PDFs, transcripts, or lecture content.
        - Always return an empty list on failure; never raise to the caller.
        - Log all errors at WARNING level.
    """

    # Subclasses may override to give a human-readable name for logging
    SOURCE_NAME: str = "unknown"

    @abstractmethod
    def fetch(self, keyword: str, max_results: int) -> list[dict]:
        """
        Scrape course metadata for *keyword* and return up to *max_results*
        course dicts.  Must never raise — catch all exceptions internally.

        Args:
            keyword:     Search term (e.g. "machine learning").
            max_results: Upper bound on results to return.

        Returns:
            List of course metadata dicts (may be empty).
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source='{self.SOURCE_NAME}'>"
