"""
scraper.py — Unified Job Scraper

Usage (dependency injection pattern):

    request = ScrapeRequest(
        search_term="python developer",
        location="Ahmedabad, Gujarat",
        target_skills=["Python", "Django", "PostgreSQL"],
        results_wanted=100,
    )
    scraper = Scraper(request)
    jobs: list[dict] = scraper.run()
"""

from __future__ import annotations

import re
import logging
import unicodedata
from typing import Optional

from pydantic import BaseModel, Field, field_validator

import pandas as pd
from jobspy import scrape_jobs

log = logging.getLogger(__name__)


# ─── Input model (dependency injection) ──────────────────────────────────────

class ScrapeRequest(BaseModel):
    """
    Pydantic model for all scrape parameters — injected by the caller.
    Nothing is hardcoded in Scraper; everything flows from here.

    Can be used directly as a FastAPI request body:
        @router.post("/scrape")
        def scrape(req: ScrapeRequest): ...

    Attributes:
        search_term     : job title / keyword to search
        location        : city or region (e.g. "Ahmedabad, Gujarat")
        target_skills   : skills to extract from LinkedIn descriptions.
                          Naukri returns its own tags from the API regardless.
        results_wanted  : max total jobs to fetch across all platforms
        country         : jobspy country_indeed value (default: "India")
        sites           : platforms to scrape (default: linkedin + naukri)
        proxies         : optional proxy list to unblock Indeed / Glassdoor
        hours_old       : only fetch jobs posted within the last N hours.
                          None (default) → no time restriction.
                          Note: this is relative ("last N hours"), not absolute.
                          For absolute date-range queries use the DB layer.
                          ⚠ LinkedIn: conflicts with easy_apply filter.
                          ⚠ Google Jobs: parameter is often ignored.
    """
    # ── Platform availability notes (from India) ──────────────────────────────
    #   linkedin  ✅ Works — HTML scraping + description-based skill extraction
    #   naukri    ✅ Works — Indian platform, native skill tags from API
    #   google    ⚠️ Intermittent — rate-limited, works with proxy
    #   indeed    ❌ DNS blocked — apis.indeed.com unreachable without proxy
    #   glassdoor ❌ DNS blocked — glassdoor.co.in unreachable without proxy
    #   ziprec    ❌ US-only — no India listings
    # ─────────────────────────────────────────────────────────────────────────

    search_term: str
    location: str
    target_skills: list[str] = Field(default_factory=list)
    results_wanted: int = Field(default=100, ge=1, le=5000)
    country: str = "India"
    sites: list[str] = Field(default_factory=lambda: ["linkedin", "naukri"])
    proxies: Optional[list[str]] = None
    hours_old: Optional[int] = Field(
        default=None,
        ge=1,
        description="Only fetch jobs posted within the last N hours. None = no restriction.",
    )

    @field_validator("search_term", "location")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("sites")
    @classmethod
    def sites_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one site must be specified")
        return v


# ─── Scraper class ────────────────────────────────────────────────────────────

class Scraper:
    """
    Unified scraper that fetches jobs from multiple platforms and returns
    a list of normalized dicts (JSON-serializable).

    Designed for dependency injection: all configuration lives in ScrapeRequest.
    """

    def __init__(self, request: ScrapeRequest) -> None:
        self.request = request

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self) -> list[dict]:
        """
        Orchestrates the full scrape pipeline:
          1. Fetch raw jobs from all configured platforms
          2. Extract / enrich skills (LinkedIn description parse + Naukri native)
          3. Normalize each row into a clean JSON-serializable dict
        Returns a list of job dicts.
        """
        log.info(
            f"Scraping '{self.request.search_term}' in '{self.request.location}' "
            f"from {self.request.sites} (limit={self.request.results_wanted})"
        )

        raw_df = self._fetch()
        if raw_df.empty:
            log.warning("No jobs returned from any platform.")
            return []

        enriched_df = self._enrich_skills(raw_df)
        result = self._normalize(enriched_df)

        log.info(
            f"Done: {len(result)} jobs | "
            f"with skills: {sum(1 for j in result if j.get('skills'))} | "
            f"by site: { {s: sum(1 for j in result if j['source'] == s) for s in self.request.sites} }"
        )
        return result

    # ── Step 1: Fetch ─────────────────────────────────────────────────────────

    def _fetch(self) -> pd.DataFrame:
        """
        Calls jobspy's scrape_jobs with the injected ScrapeRequest params.
        fetch_description=True is enabled so LinkedIn job pages are visited
        and their description text is available for skill extraction.
        """
        try:
            df = scrape_jobs(
                site_name=self.request.sites,
                search_term=self.request.search_term,
                location=self.request.location,
                results_wanted=self.request.results_wanted,
                country_indeed=self.request.country,
                fetch_description=True,      # needed for LinkedIn skill extraction
                description_format="plain",  # plain text is easiest to parse
                proxies=self.request.proxies,
                hours_old=self.request.hours_old,  # None → no restriction
            )
            log.info(f"Fetched {len(df)} raw rows")
            return df
        except Exception as exc:
            log.error(f"scrape_jobs failed: {exc}")
            return pd.DataFrame()

    # ── Step 2: Skill enrichment ──────────────────────────────────────────────

    def _enrich_skills(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        - Naukri: already has skills from the native API (comma-separated string).
        - LinkedIn: skills column is always empty; extract from description text
                    using the caller-supplied target_skills list.
        - Other platforms: same description-based extraction as LinkedIn.
        """
        if not self.request.target_skills:
            return df

        mask = df["skills"].isna() & df["description"].notna()
        df.loc[mask, "skills"] = df.loc[mask, "description"].apply(
            lambda desc: self._extract_skills(desc)
        )
        return df

    def _extract_skills(self, description: str) -> str | None:
        """
        Scans a plain-text job description and returns a comma-separated string
        of matched skills from target_skills. Uses word-boundary regex to avoid
        partial matches (e.g. 'R' won't match inside 'React').
        """
        if not description:
            return None
        text = description.lower()
        found = []
        for skill in self.request.target_skills:
            pattern = (
                r"(?<![a-z0-9\.\-])"
                + re.escape(skill.lower())
                + r"(?![a-z0-9\.\-])"
            )
            if re.search(pattern, text):
                found.append(skill)
        return ", ".join(found) if found else None

    # ── Step 3: Normalize to JSON-serializable dicts ──────────────────────────

    def _normalize(self, df: pd.DataFrame) -> list[dict]:
        """
        Maps each DataFrame row to a clean, flat dict using the project's
        job schema field names so it can be used directly with JobCreate / DB.
        """
        jobs = []
        for _, row in df.iterrows():
            jobs.append(self._row_to_dict(row))
        return jobs

    def _row_to_dict(self, row: pd.Series) -> dict:
        """Converts a single jobspy DataFrame row into a normalized job dict."""

        # Skills: Naukri returns comma-separated string; others may too after enrichment
        raw_skills = row.get("skills")
        skills: list[str] = []
        if pd.notna(raw_skills) and raw_skills:
            skills = [s.strip() for s in str(raw_skills).split(",") if s.strip()]

        # Experience: parse from experience_range string (e.g. "2-5 Yrs")
        exp_min, exp_max = self._parse_experience(row.get("experience_range"))

        # date_posted → ISO string or None
        date_posted = row.get("date_posted")
        posted_at = (
            str(date_posted) if pd.notna(date_posted) and date_posted else None
        )

        return {
            # Core fields (match JobCreate schema)
            "title":          self._safe_str(row.get("title")),
            "company":        self._safe_str(row.get("company")),
            "location":       self._safe_str(row.get("location")),
            "description":    self._clean_description(row.get("description")),
            "source":         self._safe_str(row.get("site")),
            "source_url":     self._safe_str(row.get("job_url")),
            "posted_at":      posted_at,
            "skills":         skills,
            "experience_min": exp_min,
            "experience_max": exp_max,
            # Extra metadata (not in JobCreate but useful for display / filtering)
            "source_id":      self._safe_str(row.get("id")),
            "is_remote":      bool(row.get("is_remote")) if pd.notna(row.get("is_remote")) else None,
            "job_type":       self._safe_str(row.get("job_type")),
            "job_level":      self._safe_str(row.get("job_level")),
            "company_url":    self._safe_str(row.get("company_url")),
            "company_logo":   self._safe_str(row.get("company_logo")),
            "salary_min":     self._safe_num(row.get("min_amount")),
            "salary_max":     self._safe_num(row.get("max_amount")),
            "currency":       self._safe_str(row.get("currency")),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_str(val) -> str | None:
        """Return stripped string or None for NaN / empty values."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        s = str(val).strip()
        return s if s else None

    @staticmethod
    def _clean_description(val, max_length: int = 5000) -> str | None:
        """
        Normalizes a raw job description string:
          1. NaN / empty → None
          2. Strip emoji and non-printable Unicode symbols
             (keeps letters, digits, punctuation, basic symbols)
          3. Collapse repeated whitespace and newlines into a single space
          4. Strip leading/trailing whitespace
          5. Cap at max_length characters (default 5000)
        """
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        text = str(val)

        # Remove emoji and non-printable symbols using Unicode categories:
        # Keep: L (letters), N (numbers), P (punctuation), Z (separators),
        #       Sm (math), Sc (currency), S (other symbols kept selectively)
        # Drop: So (emoji/pictographs), Cs (surrogates), Cc (control chars)
        cleaned_chars = []
        for ch in text:
            cat = unicodedata.category(ch)
            if cat in ("Cc", "Cs", "So"):   # control, surrogate, other-symbol (emoji)
                cleaned_chars.append(" ")   # replace with space so words don't merge
            else:
                cleaned_chars.append(ch)
        text = "".join(cleaned_chars)

        # Collapse all whitespace sequences (spaces, tabs, newlines) → single space
        text = re.sub(r"\s+", " ", text).strip()

        # Cap length
        if len(text) > max_length:
            text = text[:max_length].rsplit(" ", 1)[0] + "…"  # break at word boundary

        return text if text else None

    @staticmethod
    def _safe_num(val) -> float | None:
        """Return float or None for NaN values."""
        try:
            return float(val) if pd.notna(val) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_experience(experience_range: str | None) -> tuple[int | None, int | None]:
        """
        Parses strings like '2-5 Yrs', '3+ Years', '0-1 Yr' into (min, max).
        Returns (None, None) if parsing fails.
        """
        if not experience_range or not isinstance(experience_range, str):
            return None, None
        nums = re.findall(r"\d+", experience_range)
        if len(nums) >= 2:
            return int(nums[0]), int(nums[1])
        if len(nums) == 1:
            return int(nums[0]), None
        return None, None


# ─── CLI / standalone test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)

    request = ScrapeRequest(
        search_term="software engineer",
        location="Ahmedabad, Gujarat",
        target_skills=["Python", "Java", "JavaScript"],
        results_wanted=100,
    )

    scraper = Scraper(request)
    jobs = scraper.run()

    print(f"\n{'='*60}")
    print(f"Total jobs: {len(jobs)}")
    print(f"With skills: {sum(1 for j in jobs if j['skills'])}")
    print(f"{'='*60}\n")

    # Print first 5 as pretty JSON
    print(json.dumps(jobs[:5], indent=2, default=str))

    # Save all to JSON
    with open("jobs.json", "w") as f:
        json.dump(jobs, f, indent=2, default=str)
    print("\nSaved to jobs.json")
