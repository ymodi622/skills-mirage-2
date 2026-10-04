"""
scrapers/jobs — Job scraper package.

Re-exports the top-level scraper for backward compatibility so existing
imports like:
    from app.scrapers.scraper import Scraper, ScrapeRequest
continue to work unchanged while new code can also use:
    from app.scrapers.jobs import Scraper, ScrapeRequest
"""

from app.scrapers.scraper import Scraper, ScrapeRequest  # noqa: F401

__all__ = ["Scraper", "ScrapeRequest"]
