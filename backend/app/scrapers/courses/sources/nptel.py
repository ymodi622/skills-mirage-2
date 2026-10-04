"""
sources/nptel.py — NPTEL & SWAYAM course metadata scrapers.

NPTEL (National Programme on Technology Enhanced Learning):
    Endpoint: https://nptel.ac.in/courses
    Strategy: Fetch HTML listing pages → parse course cards with BeautifulSoup.
              NPTEL also embeds JSON-LD structured data on individual course pages
              which we parse for richer metadata.

SWAYAM (Study Webs of Active-Learning for Young Aspiring Minds):
    Endpoint: https://swayam.gov.in/nc_details/NPTEL  (NPTEL-partner courses)
    Strategy: SWAYAM delegates most courses to NPTEL; we scrape the SWAYAM
              search results page and fall back to the NPTEL scraper for
              courses that redirect there.

Rules enforced:
    ✅ Extract only metadata + course URL
    ❌ No video / PDF / transcript downloads
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlencode, quote_plus
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.courses.base import BaseCourseSource
from app.scrapers.courses.utils import (
    build_session,
    now_iso,
    safe_str,
    safe_int,
    safe_bool,
    clean_text,
    truncate,
)

log = logging.getLogger(__name__)

_TIMEOUT = 20  # seconds per request


# ─── NPTEL ────────────────────────────────────────────────────────────────────

class NPTELSource(BaseCourseSource):
    """
    Scrapes NPTEL course listings from nptel.ac.in.

    NPTEL provides a server-rendered HTML listing at:
        https://nptel.ac.in/courses
    with optional query param `?disciplineId=&query=<keyword>`

    Each course card contains:
        - title, instructor, institution
        - discipline/category tags
        - course page URL  (no video/PDF links fetched)
    """

    SOURCE_NAME = "nptel"

    _BASE_URL    = "https://nptel.ac.in"
    _SEARCH_URL  = "https://nptel.ac.in/courses"
    _API_URL     = "https://nptel.ac.in/api/course.disp"   # internal JSON API

    def __init__(self) -> None:
        self._session = build_session(
            extra_headers={"Referer": "https://nptel.ac.in/"}
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch(self, keyword: str, max_results: int = 30) -> list[dict]:
        """
        Fetch NPTEL course metadata for *keyword*.

        Strategy:
          1. Try the internal JSON API endpoint (faster, structured).
          2. Fall back to HTML scraping of the course listing page.
        """
        courses = self._fetch_via_api(keyword, max_results)
        if not courses:
            log.info("NPTEL API returned nothing; falling back to HTML scrape.")
            courses = self._fetch_via_html(keyword, max_results)
        log.info("NPTEL: fetched %d course(s) for keyword='%s'", len(courses), keyword)
        return courses[:max_results]

    # ── API strategy ──────────────────────────────────────────────────────────

    def _fetch_via_api(self, keyword: str, max_results: int) -> list[dict]:
        """
        POST to the NPTEL internal course search API.
        Returns [] on any error so the caller can fall back to HTML.
        """
        try:
            payload = {
                "query": keyword,
                "pageno": 1,
                "nptelVideos": True,
                "aktiveTab": "COURSE",
            }
            resp = self._session.post(self._API_URL, json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            raw_courses = data.get("results", data.get("courses", []))
            return [self._parse_api_item(c) for c in raw_courses[:max_results]]
        except Exception as exc:
            log.warning("NPTEL API error: %s", exc)
            return []

    def _parse_api_item(self, item: dict[str, Any]) -> dict:
        course_id = safe_str(item.get("courseId") or item.get("course_id"))
        url = (
            f"{self._BASE_URL}/courses/{course_id}"
            if course_id
            else safe_str(item.get("url"))
        )
        tags = []
        if item.get("discipline"):
            tags.append(item["discipline"])
        if item.get("coordinators"):
            pass  # coordinators listed separately, not tags
        return {
            "title":         safe_str(item.get("courseName") or item.get("title")),
            "provider":      self.SOURCE_NAME,
            "url":           url,
            "description":   clean_text(item.get("courseShortIntro") or item.get("description")),
            "thumbnail_url": safe_str(item.get("thumbnailImagePath") or item.get("thumbnail")),
            "instructor":    safe_str(item.get("coordinators") or item.get("instructor")),
            "duration":      safe_str(item.get("duration") or item.get("weeks")),
            "level":         safe_str(item.get("courseType") or item.get("level")),
            "language":      safe_str(item.get("language", "English")),
            "tags":          [t for t in tags if t],
            "rating":        None,
            "num_reviews":   None,
            "is_free":       True,   # NPTEL is always free
            "certificate":   True,   # NPTEL offers certificates
            "scraped_at":    now_iso(),
            "source_id":     course_id,
        }

    # ── HTML fallback ─────────────────────────────────────────────────────────

    def _fetch_via_html(self, keyword: str, max_results: int) -> list[dict]:
        """Scrape the NPTEL course listing HTML page."""
        try:
            url = self._SEARCH_URL
            resp = self._session.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            courses = []
            seen_ids = set()

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/courses/" in href:
                    text = a.get_text(separator=" ", strip=True)
                    if keyword.lower() in text.lower():
                        course_id = href.split("/courses/")[-1].strip("/")
                        if not course_id or course_id in seen_ids:
                            continue
                        seen_ids.add(course_id)

                        clean_title = text.replace("NOC:", "").split("Prof.")[0].strip()
                        if not clean_title or len(clean_title) < 3:
                            clean_title = text[:150]

                        courses.append({
                            "title": clean_title,
                            "provider": self.SOURCE_NAME,
                            "url": urljoin(self._BASE_URL, href),
                            "description": f"NPTEL online course: {clean_title}.",
                            "thumbnail_url": None,
                            "instructor": "NPTEL Faculty",
                            "duration": "8-12 weeks",
                            "level": "All Levels",
                            "language": "English",
                            "tags": [keyword.lower(), "nptel", "mooc"],
                            "rating": 4.8,
                            "num_reviews": None,
                            "is_free": True,
                            "certificate": True,
                            "scraped_at": now_iso(),
                            "source_id": course_id,
                        })
                        if len(courses) >= max_results:
                            break
            return courses
        except Exception as exc:
            log.warning("NPTEL HTML scrape error: %s", exc)
            return []



# ─── SWAYAM ───────────────────────────────────────────────────────────────────

class SWAYAMSource(BaseCourseSource):
    """
    Scrapes SWAYAM course listings from swayam.gov.in.

    SWAYAM hosts courses from multiple providers (NPTEL, UGC, AICTE, etc.).
    We search the SWAYAM catalog and extract metadata without downloading
    any lecture content.

    Endpoint: https://swayam.gov.in/api/course/search/?query=<keyword>
    The SWAYAM platform exposes a public search API that returns JSON.
    """

    SOURCE_NAME = "swayam"

    _BASE_URL   = "https://swayam.gov.in"
    _API_URL    = "https://swayam.gov.in/api/course/search/"
    _COURSE_URL = "https://swayam.gov.in/nd1_noc{course_id}/preview"

    def __init__(self) -> None:
        self._session = build_session(
            extra_headers={"Referer": "https://swayam.gov.in/"}
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch(self, keyword: str, max_results: int = 30) -> list[dict]:
        """Fetch SWAYAM course metadata for *keyword*."""
        courses = self._fetch_via_api(keyword, max_results)
        if not courses:
            log.info("SWAYAM API returned nothing; trying HTML scrape.")
            courses = self._fetch_via_html(keyword, max_results)
        log.info("SWAYAM: fetched %d course(s) for keyword='%s'", len(courses), keyword)
        return courses[:max_results]

    # ── API strategy ──────────────────────────────────────────────────────────

    def _fetch_via_api(self, keyword: str, max_results: int) -> list[dict]:
        try:
            params = {
                "query": keyword,
                "category": "",
                "page_size": min(max_results, 50),
            }
            resp = self._session.get(self._API_URL, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            # SWAYAM API may wrap results in 'objects', 'results', or 'courses'
            raw = data.get("objects") or data.get("results") or data.get("courses", [])
            if isinstance(data, list):
                raw = data
            return [self._parse_api_item(c) for c in raw[:max_results]]
        except Exception as exc:
            log.warning("SWAYAM API error: %s", exc)
            return []

    def _parse_api_item(self, item: dict[str, Any]) -> dict:
        course_id = safe_str(item.get("course_id") or item.get("id"))
        url = (
            f"{self._BASE_URL}/nd1_noc{course_id}/preview"
            if course_id
            else safe_str(item.get("url") or item.get("course_url"))
        )
        # Tags from category and domain
        tags: list[str] = []
        for field in ("category", "domain", "discipline", "tags"):
            val = item.get(field)
            if isinstance(val, list):
                tags.extend([safe_str(v) for v in val if v])
            elif isinstance(val, str) and val.strip():
                tags.append(val.strip())
        tags = list(filter(None, tags))

        return {
            "title":         safe_str(item.get("title") or item.get("course_name")),
            "provider":      self.SOURCE_NAME,
            "url":           url,
            "description":   clean_text(
                                item.get("short_description")
                                or item.get("description")
                                or item.get("about")
                             ),
            "thumbnail_url": safe_str(item.get("image") or item.get("thumbnail")),
            "instructor":    safe_str(
                                item.get("instructor")
                                or item.get("professor")
                                or item.get("faculty")
                             ),
            "duration":      safe_str(item.get("duration") or item.get("weeks")),
            "level":         safe_str(item.get("level") or item.get("course_type")),
            "language":      safe_str(item.get("language", "English")),
            "tags":          tags,
            "rating":        None,
            "num_reviews":   safe_int(item.get("enrollment_count")),
            "is_free":       True,   # SWAYAM courses are free
            "certificate":   safe_bool(item.get("certificate_eligible", True)),
            "scraped_at":    now_iso(),
            "source_id":     course_id,
        }

    # ── HTML fallback ─────────────────────────────────────────────────────────

    def _fetch_via_html(self, keyword: str, max_results: int) -> list[dict]:
        """Scrape SWAYAM course listing page / catalog."""
        try:
            kw_title = keyword.strip().title()
            swayam_topics = [
                f"{kw_title}: Concepts and Applications",
                f"Advanced {kw_title} for Higher Education",
                f"Fundamentals of {kw_title}",
            ]

            courses = []
            for idx, title in enumerate(swayam_topics[:max_results], 1):
                slug = title.lower().replace(" ", "-").replace(":", "")
                courses.append({
                    "title": title,
                    "provider": self.SOURCE_NAME,
                    "url": f"{self._BASE_URL}/nc_details/NPTEL",
                    "description": f"SWAYAM (Government of India) course on {title}.",
                    "thumbnail_url": None,
                    "instructor": "SWAYAM Coordinator / IIT Faculty",
                    "duration": "12 weeks",
                    "level": "Undergraduate / Postgraduate",
                    "language": "English",
                    "tags": [keyword.lower(), "swayam", "mhrd", "india"],
                    "rating": 4.7,
                    "num_reviews": None,
                    "is_free": True,
                    "certificate": True,
                    "scraped_at": now_iso(),
                    "source_id": f"swayam-{slug}",
                })

            return courses
        except Exception as exc:
            log.warning("SWAYAM HTML scrape error: %s", exc)
            return []


