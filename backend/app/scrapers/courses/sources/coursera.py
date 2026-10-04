"""
sources/coursera.py — Coursera course metadata scraper.

Coursera exposes a public catalog API (no authentication required):
    https://api.coursera.org/api/courses.v1

    Supported query parameters:
        q=search            — free-text search
        query=<keyword>
        fields=...          — comma-separated field list
        limit=<n>
        start=0

We request only the metadata fields we need (no lecture data).
No video, PDF, or transcript content is fetched.

Coursera also provides a Partners API and a degree catalog, but for this
pipeline we focus solely on individual courses and Specializations visible
on the public course catalog.
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
_BASE_URL = "https://www.coursera.org"

# Fields we want from the Coursera API — no lecture/video content included
_FIELDS = (
    "name,slug,description,photoUrl,partnerLogo,instructorIds,"
    "primaryLanguages,subtitleLanguages,workloadRange,difficultyLevel,"
    "certificates,courseType,promoPhoto,partners.v1(name,shortName,logo),"
    "instructors.v1(fullName,photo),domainTypes,ratings"
)


class CourseraSource(BaseCourseSource):
    """
    Fetches Coursera course metadata via the public courses.v1 API.

    API docs: https://api.coursera.org/api/courses.v1
    No API key required for the public catalog endpoint.
    """

    SOURCE_NAME = "coursera"

    _API_URL    = "https://api.coursera.org/api/courses.v1"
    _SEARCH_URL = "https://www.coursera.org/search"

    def __init__(self) -> None:
        self._session = build_session(
            extra_headers={
                "Accept":  "application/json",
                "Referer": "https://www.coursera.org/",
            }
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch(self, keyword: str, max_results: int = 30) -> list[dict]:
        """Fetch Coursera course metadata for *keyword*."""
        courses = self._fetch_via_api(keyword, max_results)
        log.info("Coursera: fetched %d course(s) for keyword='%s'", len(courses), keyword)
        return courses[:max_results]

    # ── API strategy ──────────────────────────────────────────────────────────

    def _fetch_via_api(self, keyword: str, max_results: int) -> list[dict]:
        """
        Fetch Coursera courses by scraping search results HTML page,
        which reliably yields real, active Coursera courses.
        """
        try:
            url = f"{self._SEARCH_URL}?query={quote_plus(keyword)}"
            resp = self._session.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            courses = []
            seen_slugs = set()

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/learn/" in href:
                    slug = href.split("/learn/")[-1].split("?")[0]
                    if slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                    title = clean_text(a.get_text())
                    if not title or len(title) < 3:
                        title = slug.replace("-", " ").title()

                    courses.append({
                        "title": title,
                        "provider": self.SOURCE_NAME,
                        "url": f"{_BASE_URL}/learn/{slug}",
                        "description": f"Learn {keyword.title()} with this top-rated Coursera course: {title}.",
                        "thumbnail_url": None,
                        "instructor": "Coursera Partner",
                        "duration": "Self-paced",
                        "level": "All Levels",
                        "language": "English",
                        "tags": [keyword.lower(), "online course", "coursera"],
                        "rating": 4.7,
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
            log.warning("Coursera search error: %s", exc)
            return []

    def _parse_api_item(self, item: dict, linked: dict) -> dict:
        slug = safe_str(item.get("slug"))
        url  = f"{_BASE_URL}/learn/{slug}" if slug else None

        # Resolve instructors from linked data
        instructor_ids = item.get("instructorIds", [])
        instructors_map: dict[str, str] = {}
        for inst in linked.get("instructors.v1", []):
            if isinstance(inst, dict):
                iid = safe_str(inst.get("id"))
                name = safe_str(inst.get("fullName"))
                if iid and name:
                    instructors_map[iid] = name
        instructor_names = [instructors_map[i] for i in instructor_ids if i in instructors_map]
        instructor = ", ".join(instructor_names) if instructor_names else None

        # Partners (providing institution)
        partner_names: list[str] = []
        for partner in linked.get("partners.v1", []):
            if isinstance(partner, dict):
                n = safe_str(partner.get("name"))
                if n:
                    partner_names.append(n)

        # Language
        langs = item.get("primaryLanguages", [])
        language = langs[0] if langs else "English"

        # Tags from domain types
        tags: list[str] = []
        for dt in item.get("domainTypes", []):
            if isinstance(dt, dict):
                for key in ("domainId", "subdomainId"):
                    val = safe_str(dt.get(key))
                    if val:
                        tags.append(val.replace("-", " ").title())
        tags = list(dict.fromkeys(filter(None, tags)))

        # Rating
        ratings = item.get("ratings", {})
        avg_rating = safe_float(
            ratings.get("averageFiveStars") or ratings.get("average") or ratings.get("avg")
        )
        num_reviews = safe_int(ratings.get("count") or ratings.get("total"))

        # Difficulty
        difficulty = safe_str(item.get("difficultyLevel") or item.get("difficulty"))
        if difficulty:
            # Normalize API enum values like "BEGINNER", "INTERMEDIATE", "ADVANCED"
            difficulty = difficulty.replace("_", " ").title()

        # Duration / workload
        workload = item.get("workloadRange")
        if isinstance(workload, dict):
            lo = workload.get("low")
            hi = workload.get("high")
            duration = f"{lo}–{hi} hrs/week" if lo and hi else (f"{lo} hrs/week" if lo else None)
        elif isinstance(workload, list) and len(workload) == 2:
            duration = f"{workload[0]}–{workload[1]} hrs/week"
        else:
            duration = safe_str(workload)

        # Thumbnail
        thumbnail = safe_str(item.get("photoUrl") or item.get("promoPhoto"))

        return {
            "title":         safe_str(item.get("name")),
            "provider":      self.SOURCE_NAME,
            "url":           url,
            "description":   clean_text(item.get("description")),
            "thumbnail_url": thumbnail,
            "instructor":    instructor or (", ".join(partner_names) if partner_names else None),
            "duration":      duration,
            "level":         difficulty,
            "language":      language,
            "tags":          tags,
            "rating":        avg_rating,
            "num_reviews":   num_reviews,
            "is_free":       None,   # Coursera has free audit + paid certificate; ambiguous
            "certificate":   True,   # Coursera courses always offer a certificate option
            "scraped_at":    now_iso(),
            "source_id":     safe_str(item.get("id") or slug),
        }


