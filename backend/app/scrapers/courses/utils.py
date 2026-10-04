"""
utils.py — Shared helpers for the course scraper pipeline.

Provides:
    - build_session()   : pre-configured requests.Session with headers & retries
    - now_iso()         : current UTC timestamp as ISO-8601 string
    - safe_str()        : coerce any value to stripped str or None
    - safe_float()      : coerce any value to float or None
    - safe_int()        : coerce any value to int or None
    - safe_bool()       : coerce any value to bool or None
    - clean_text()      : strip HTML tags, collapse whitespace
    - truncate()        : cap a string at N characters on a word boundary
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

# ── Default browser-like headers sent with every request ─────────────────────

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── HTML tag stripper regex ───────────────────────────────────────────────────
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


# ─── Session factory ──────────────────────────────────────────────────────────

def build_session(
    timeout: int = 15,
    retries: int = 3,
    backoff_factor: float = 0.5,
    extra_headers: dict[str, str] | None = None,
) -> requests.Session:
    """
    Return a requests.Session with:
      - Retry on 429 / 5xx with exponential backoff
      - Default browser-like headers
      - Caller-supplied extra headers merged on top
      - Reasonable read/connect timeout (set per-request via the adapter)

    The session does NOT set a global timeout — pass `timeout=` on each
    individual `session.get()` / `session.post()` call.

    Args:
        timeout:       Default socket timeout in seconds (informational only —
                       callers must still pass timeout= to each request).
        retries:       Max retry attempts for transient errors.
        backoff_factor: Exponential back-off multiplier between retries.
        extra_headers: Platform-specific headers to merge on top of defaults.

    Returns:
        Configured requests.Session instance.
    """
    session = requests.Session()

    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    headers = dict(_DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    session.headers.update(headers)

    return session


# ─── Timestamp ────────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (e.g. '2026-10-03T07:00:00Z')."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Type-safe coercions ──────────────────────────────────────────────────────

def safe_str(val: Any, max_len: int | None = None) -> str | None:
    """
    Coerce *val* to a stripped string or None.

    Args:
        val:     Any value — None, NaN, int, str, etc.
        max_len: Optional character cap; truncates at a word boundary.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "n/a"):
        return None
    if max_len and len(s) > max_len:
        s = truncate(s, max_len)
    return s


def safe_float(val: Any) -> float | None:
    """Coerce *val* to float or None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f   # NaN check
    except (TypeError, ValueError):
        return None


def safe_int(val: Any) -> int | None:
    """Coerce *val* to int or None (rounds floats)."""
    f = safe_float(val)
    return int(round(f)) if f is not None else None


def safe_bool(val: Any) -> bool | None:
    """
    Coerce common truthy/falsy representations to bool or None.
    Handles: True/False, 1/0, 'true'/'false', 'yes'/'no', 'free'/'paid'.
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).lower().strip()
    if s in ("true", "1", "yes", "free"):
        return True
    if s in ("false", "0", "no", "paid"):
        return False
    return None


# ─── Text helpers ─────────────────────────────────────────────────────────────

def clean_text(text: Any) -> str | None:
    """
    Strip HTML tags, collapse whitespace, and return a clean string or None.
    """
    s = safe_str(text)
    if not s:
        return None
    # Remove HTML tags
    s = _HTML_TAG_RE.sub(" ", s)
    # Decode common HTML entities
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
         .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s if s else None


def truncate(text: str, max_len: int) -> str:
    """
    Cap *text* at *max_len* characters, breaking at a word boundary and
    appending '…' if truncation occurred.
    """
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut + "…"


# ─── Deduplication ────────────────────────────────────────────────────────────

def deduplicate_courses(courses: list[dict]) -> list[dict]:
    """
    Remove duplicate course entries.  Two courses are considered duplicates
    if they share the same canonical URL.  When a URL is absent, the title
    (lowercased + stripped) is used as the dedup key.

    The first occurrence of each key is kept; subsequent duplicates are
    dropped and logged.

    Args:
        courses: Raw combined list from all sources.

    Returns:
        Deduplicated list preserving original order.
    """
    seen: set[str] = set()
    unique: list[dict] = []

    for course in courses:
        url = safe_str(course.get("url"))
        title = safe_str(course.get("title"))
        key = url if url else (title.lower() if title else None)

        if key is None:
            # No key available — keep it to avoid silent data loss
            unique.append(course)
            continue

        if key in seen:
            log.debug("Dedup: dropping duplicate course key='%s'", key)
            continue

        seen.add(key)
        unique.append(course)

    dropped = len(courses) - len(unique)
    if dropped:
        log.info("Deduplication removed %d duplicate(s); %d remain", dropped, len(unique))

    return unique
