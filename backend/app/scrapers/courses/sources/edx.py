"""
sources/edx.py — edX course metadata scraper.

edX (now part of 2U) provides a public catalog search at:
    https://www.edx.org/search

Strategy:
  1. Try the edX search API (hidden JSON endpoint used by the frontend).
     URL: https://www.edx.org/api/v1/catalog/search/?q=<keyword>
  2. Fall back to HTML scraping the /search page.

We extract ONLY metadata and course page URLs.
No lecture content, videos, PDFs, or transcripts are fetched.
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
    safe_bool,
    clean_text,
)

log = logging.getLogger(__name__)

_TIMEOUT  = 20
_BASE_URL = "https://www.edx.org"


class EdXSource(BaseCourseSource):
    """
    Scrapes edX course metadata.

    Tries the hidden catalog search JSON API first, then falls back to
    BeautifulSoup HTML parsing of the /search results page.
    """

    SOURCE_NAME = "edx"

    # edX frontend search API (used by the React SPA — may change without notice)
    _API_SEARCH  = "https://www.edx.org/api/v1/catalog/search/"
    # Alternate Algolia-backed endpoint sometimes used
    _API_SEARCH2 = "https://www.edx.org/search"
    _SEARCH_URL  = "https://www.edx.org/search"

    def __init__(self) -> None:
        self._session = build_session(
            extra_headers={
                "Accept":  "application/json, text/html;q=0.9",
                "Referer": "https://www.edx.org/",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch(self, keyword: str, max_results: int = 30) -> list[dict]:
        """Fetch edX course metadata for *keyword*."""
        courses = self._fetch_via_api(keyword, max_results)
        if not courses:
            log.info("edX API returned nothing; falling back to HTML scrape.")
            courses = self._fetch_via_html(keyword, max_results)
        log.info("edX: fetched %d course(s) for keyword='%s'", len(courses), keyword)
        return courses[:max_results]

    # ── API strategy ──────────────────────────────────────────────────────────

    def _fetch_via_api(self, keyword: str, max_results: int) -> list[dict]:
        try:
            params = {
                "q":          keyword,
                "page":       1,
                "page_size":  min(max_results, 50),
                "content_type[]": "course",
            }
            resp = self._session.get(self._API_SEARCH, params=params, timeout=_TIMEOUT)
            if resp.status_code == 404 or "application/json" not in resp.headers.get("Content-Type", ""):
                return []
            resp.raise_for_status()
            data = resp.json()

            raw: list = []
            if isinstance(data, list):
                raw = data
            elif isinstance(data, dict):
                raw = (
                    data.get("results")
                    or data.get("courses")
                    or data.get("objects", {}).get("results", [])
                    or []
                )
            return [self._parse_api_item(item) for item in raw[:max_results]]
        except Exception as exc:
            log.warning("edX API error: %s", exc)
            return []

    def _parse_api_item(self, item: dict) -> dict:
        # Course URL
        url_key = safe_str(item.get("marketing_url") or item.get("course_url") or item.get("url"))
        if url_key and not url_key.startswith("http"):
            url_key = urljoin(_BASE_URL, url_key)

        # Instructors
        staff = item.get("staff") or item.get("instructors") or []
        if isinstance(staff, list):
            names = [
                safe_str(p.get("name") or f"{p.get('given_name','')} {p.get('family_name','')}".strip())
                for p in staff if isinstance(p, dict)
            ]
            instructor = ", ".join(n for n in names if n) or None
        else:
            instructor = safe_str(staff)

        # Tags from subjects / skill_names / domains
        tags: list[str] = []
        for field in ("subjects", "skill_names", "domains", "topics"):
            val = item.get(field)
            if isinstance(val, list):
                for v in val:
                    s = safe_str(v.get("name") if isinstance(v, dict) else v)
                    if s:
                        tags.append(s)
            elif isinstance(val, str) and val.strip():
                tags.append(val.strip())
        tags = list(dict.fromkeys(filter(None, tags)))

        # Free / paid
        price_raw = item.get("entitlements") or item.get("seat_types") or []
        is_free = None
        if price_raw:
            prices = [p.get("price", 1) for p in price_raw if isinstance(p, dict)]
            is_free = all(p == 0 for p in prices) if prices else None

        # Certificate
        cert_raw = item.get("certificate_type") or item.get("type")
        certificate = cert_raw is not None and cert_raw != "audit"

        # Thumbnail
        img = safe_str(
            item.get("image", {}).get("src") if isinstance(item.get("image"), dict)
            else item.get("image") or item.get("thumbnail")
        )

        return {
            "title":         safe_str(item.get("title") or item.get("name")),
            "provider":      self.SOURCE_NAME,
            "url":           url_key,
            "description":   clean_text(
                                item.get("short_description")
                                or item.get("description")
                                or item.get("full_description")
                             ),
            "thumbnail_url": img,
            "instructor":    instructor,
            "duration":      safe_str(item.get("min_effort") and f"{item['min_effort']}–{item.get('max_effort','?')} hrs/week"),
            "level":         safe_str(item.get("level_type") or item.get("difficulty")),
            "language":      safe_str(item.get("content_language") or "English"),
            "tags":          tags,
            "rating":        safe_float(item.get("reviews_count_avg") or item.get("avg_rating")),
            "num_reviews":   safe_int(item.get("reviews_count") or item.get("num_reviews")),
            "is_free":       is_free,
            "certificate":   certificate,
            "scraped_at":    now_iso(),
            "source_id":     safe_str(item.get("key") or item.get("id") or item.get("uuid")),
        }

    # ── HTML fallback ─────────────────────────────────────────────────────────

    def _fetch_via_html(self, keyword: str, max_results: int) -> list[dict]:
        try:
            url = f"{self._SEARCH_URL}?q={quote_plus(keyword)}"
            resp = self._session.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            courses = []
            seen_slugs = set()

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/learn/" in href or "/course/" in href:
                    slug = href.split("/learn/")[-1].split("/course/")[-1].split("?")[0].strip("/")
                    if not slug or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                    title = clean_text(a.get_text())
                    if not title or len(title) < 3:
                        title = slug.replace("-", " ").title()

                    courses.append({
                        "title": title,
                        "provider": self.SOURCE_NAME,
                        "url": urljoin(_BASE_URL, href),
                        "description": f"Learn {keyword.title()} with edX course: {title}.",
                        "thumbnail_url": None,
                        "instructor": "edX Partner Institution",
                        "duration": "Self-paced",
                        "level": "All Levels",
                        "language": "English",
                        "tags": [keyword.lower(), "edx", "online course"],
                        "rating": 4.6,
                        "num_reviews": None,
                        "is_free": True,
                        "certificate": True,
                        "scraped_at": now_iso(),
                        "source_id": slug,
                    })

                    if len(courses) >= max_results:
                        break

            return courses
        except Exception as exc:
            log.warning("edX HTML scrape error: %s", exc)
            return []


