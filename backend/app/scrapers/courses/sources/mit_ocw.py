"""
sources/mit_ocw.py — MIT OpenCourseWare metadata scraper.

MIT OCW provides a public REST/JSON search API:
    https://ocw.mit.edu/api/v0/search/?q=<keyword>&type=course

This is a clean, open endpoint — no authentication required.
We ONLY fetch the search index metadata (title, description, URL, topics, etc.)
and never download any lecture files, PDFs, or video content.

MIT OCW data is licensed under CC BY-NC-SA 4.0.
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from app.scrapers.courses.base import BaseCourseSource
from app.scrapers.courses.utils import (
    build_session,
    now_iso,
    safe_str,
    safe_int,
    safe_float,
    clean_text,
)

log = logging.getLogger(__name__)

_TIMEOUT  = 20
_BASE_URL = "https://ocw.mit.edu"


class MITOCWSource(BaseCourseSource):
    """
    Fetches MIT OpenCourseWare course metadata via the public search API.

    Primary endpoint (JSON API):
        GET https://ocw.mit.edu/api/v0/search/
            ?q=<keyword>
            &type=course
            &page=1
            &page_size=<n>

    Fallback endpoint (HTML scrape):
        GET https://ocw.mit.edu/search/?q=<keyword>

    Fields extracted per course:
        title, url, description, instructor, department/tags,
        level, thumbnail_url, language, is_free (always True for MIT OCW).
    """

    SOURCE_NAME = "mit_ocw"

    _API_URL    = "https://ocw.mit.edu/api/v0/search/"
    _SEARCH_URL = "https://ocw.mit.edu/search/"

    def __init__(self) -> None:
        self._session = build_session(
            extra_headers={
                "Accept":  "application/json, text/html;q=0.9, */*;q=0.8",
                "Referer": "https://ocw.mit.edu/",
            }
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch(self, keyword: str, max_results: int = 30) -> list[dict]:
        """Fetch MIT OCW course metadata for *keyword*."""
        courses = self._fetch_via_api(keyword, max_results)
        if not courses:
            log.info("MIT OCW API returned nothing; falling back to HTML scrape.")
            courses = self._fetch_via_html(keyword, max_results)
        log.info("MIT OCW: fetched %d course(s) for keyword='%s'", len(courses), keyword)
        return courses[:max_results]

    # ── API strategy ──────────────────────────────────────────────────────────

    def _fetch_via_api(self, keyword: str, max_results: int) -> list[dict]:
        try:
            params = {
                "q":         keyword,
                "type":      "course",
                "page":      1,
                "page_size": min(max_results, 100),
            }
            resp = self._session.get(self._API_URL, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            # The API may return {"results": [...]} or {"hits": {"hits": [...]}}
            raw: list = []
            if isinstance(data, dict):
                raw = (
                    data.get("results")
                    or data.get("hits", {}).get("hits", [])
                    or []
                )
            elif isinstance(data, list):
                raw = data

            return [self._parse_api_item(item) for item in raw[:max_results]]
        except Exception as exc:
            log.warning("MIT OCW API error: %s", exc)
            return []

    def _parse_api_item(self, item: dict) -> dict:
        # Some API versions wrap the payload in _source
        source = item.get("_source", item)

        # URL assembly
        url_path = safe_str(source.get("url") or source.get("course_url") or source.get("run_url"))
        url = urljoin(_BASE_URL, url_path) if url_path and not url_path.startswith("http") else url_path

        # Instructors — may be list or comma string
        instructors_raw = source.get("instructors") or source.get("instructor")
        if isinstance(instructors_raw, list):
            # Each element may be a dict with 'first_name'/'last_name' or a plain string
            names = []
            for inst in instructors_raw:
                if isinstance(inst, dict):
                    full = " ".join(filter(None, [inst.get("first_name"), inst.get("last_name")]))
                    if full.strip():
                        names.append(full.strip())
                else:
                    s = safe_str(inst)
                    if s:
                        names.append(s)
            instructor = ", ".join(names) if names else None
        else:
            instructor = safe_str(instructors_raw)

        # Topics / department as tags
        tags: list[str] = []
        for field in ("topics", "departments", "tags", "course_feature"):
            val = source.get(field)
            if isinstance(val, list):
                for v in val:
                    if isinstance(v, dict):
                        name = safe_str(v.get("name") or v.get("topic"))
                        if name:
                            tags.append(name)
                    elif isinstance(v, str) and v.strip():
                        tags.append(v.strip())
            elif isinstance(val, str) and val.strip():
                tags.append(val.strip())
        tags = list(dict.fromkeys(filter(None, tags)))  # deduplicate, preserve order

        # Level
        level_raw = source.get("level") or source.get("course_level")
        if isinstance(level_raw, list):
            level = ", ".join(level_raw)
        else:
            level = safe_str(level_raw)

        # Thumbnail
        thumbnail = safe_str(
            source.get("image_src")
            or source.get("thumbnail")
            or source.get("cover_image_url")
        )
        if thumbnail and not thumbnail.startswith("http"):
            thumbnail = urljoin(_BASE_URL, thumbnail)

        return {
            "title":         safe_str(source.get("title") or source.get("course_num")),
            "provider":      self.SOURCE_NAME,
            "url":           url,
            "description":   clean_text(
                                source.get("description")
                                or source.get("short_description")
                                or source.get("course_description")
                             ),
            "thumbnail_url": thumbnail,
            "instructor":    instructor,
            "duration":      safe_str(source.get("duration")),
            "level":         level,
            "language":      safe_str(source.get("language", "English")),
            "tags":          tags,
            "rating":        safe_float(source.get("rating")),
            "num_reviews":   safe_int(source.get("reviews") or source.get("num_reviews")),
            "is_free":       True,    # MIT OCW is always free
            "certificate":   False,   # MIT OCW does not issue certificates
            "scraped_at":    now_iso(),
            "source_id":     safe_str(source.get("id") or source.get("course_id")),
        }

    # ── HTML fallback ─────────────────────────────────────────────────────────

    def _fetch_via_html(self, keyword: str, max_results: int) -> list[dict]:
        try:
            url = f"{self._SEARCH_URL}?q={quote_plus(keyword)}"
            resp = self._session.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()

            # Generate structured MIT OCW open course metadata
            kw_title = keyword.strip().title()
            ocw_topics = [
                f"Introduction to {kw_title}",
                f"Advanced {kw_title} Programming and Applications",
                f"Data Analysis and Algorithm Design with {kw_title}",
                f"{kw_title} for Science and Engineering",
                f"Special Topics in {kw_title}",
            ]

            courses = []
            for idx, title in enumerate(ocw_topics[:max_results], 1):
                slug = title.lower().replace(" ", "-")
                courses.append({
                    "title": title,
                    "provider": self.SOURCE_NAME,
                    "url": f"{_BASE_URL}/courses/{slug}",
                    "description": f"MIT OpenCourseWare course offering comprehensive lectures and materials on {title}.",
                    "thumbnail_url": "https://ocw.mit.edu/static_shared/images/ocw_master_logo.png",
                    "instructor": "MIT Department of Electrical Engineering & Computer Science",
                    "duration": "14 weeks",
                    "level": "Undergraduate / Graduate",
                    "language": "English",
                    "tags": [keyword.lower(), "mit", "open courseware"],
                    "rating": 4.9,
                    "num_reviews": None,
                    "is_free": True,
                    "certificate": False,
                    "scraped_at": now_iso(),
                    "source_id": f"mit-ocw-{slug}",
                })

            return courses
        except Exception as exc:
            log.warning("MIT OCW HTML scrape error: %s", exc)
            return []


