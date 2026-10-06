"""
skill_extractor.py — LLM-powered skill extraction from job descriptions.

Uses Google Gemini Flash for cost-effective, high-throughput extraction.
Processes JDs in async batches of BATCH_SIZE to stay within rate limits.
Caches results by MD5 hash of the description to avoid re-calling the LLM
for identical text across multiple analysis runs.

Setup:
    Add GEMINI_API_KEY to your .env file.
    pip install google-generativeai
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os

log = logging.getLogger(__name__)

# Maximum parallel LLM calls per batch
BATCH_SIZE = 20

# Maximum characters of JD text to send to the LLM (keeps token cost low)
MAX_JD_CHARS = 3000

_SYSTEM_PROMPT = """\
You are a technical recruiter assistant.
Extract all skills, technologies, tools, and frameworks mentioned in the job description.
Return ONLY a valid JSON array of strings — no explanation, no markdown, no wrapping object.

Example output:
["Python", "FastAPI", "Docker", "PostgreSQL", "AWS"]

Rules:
- Normalize skill names to their canonical form (e.g. "JS" → "JavaScript", "k8s" → "Kubernetes")
- Include programming languages, frameworks, libraries, cloud platforms, databases, DevOps tools
- Exclude soft skills like "communication" or "teamwork"
- If no technical skills are found, return an empty array: []
"""


class SkillExtractor:
    """
    Extracts skills from job description text using an LLM.

    Usage:
        extractor = SkillExtractor()
        skills = await extractor.batch_extract(["JD text 1", "JD text 2"])
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._cache: dict[str, list[str]] = {}   # md5 → skills
        self._client = None                       # lazy-initialized

    def _get_client(self):
        """Lazy-initialize the Gemini client so import errors are deferred."""
        if self._client is None:
            try:
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=self._api_key)
                self._client = genai.GenerativeModel(
                    model_name="gemini-3.5-flash-lite",
                    system_instruction=_SYSTEM_PROMPT,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "google-generativeai is not installed. "
                    "Run: pip install google-generativeai"
                ) from exc
        return self._client

    # ── Public API ────────────────────────────────────────────────────────────

    async def extract_skills(self, text: str) -> list[str]:
        """Extract skills from a single JD text string."""
        results = await self.batch_extract([text])
        return results[0] if results else []

    async def batch_extract(self, texts: list[str]) -> list[list[str]]:
        """
        Extract skills from a list of JD texts in parallel batches.

        Returns a list of skill lists in the same order as input texts.
        On any per-item error, returns [] for that item without aborting.
        """
        if not texts:
            return []

        results: list[list[str]] = [[] for _ in texts]

        # Split into chunks of BATCH_SIZE
        for chunk_start in range(0, len(texts), BATCH_SIZE):
            chunk = texts[chunk_start : chunk_start + BATCH_SIZE]
            chunk_results = await asyncio.gather(
                *[self._extract_one(text) for text in chunk],
                return_exceptions=False,
            )
            for i, skills in enumerate(chunk_results):
                results[chunk_start + i] = skills

        return results

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _extract_one(self, text: str) -> list[str]:
        """
        Extract skills from one JD. Checks cache first.
        Truncates text to MAX_JD_CHARS before sending to the LLM.
        """
        if not text or not text.strip():
            return []

        # Truncate to keep token cost predictable
        truncated = text[:MAX_JD_CHARS]

        # Cache lookup by MD5 hash of the (truncated) text
        cache_key = hashlib.md5(truncated.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        skills = await self._call_llm(truncated)
        self._cache[cache_key] = skills
        return skills

    async def _call_llm(self, text: str) -> list[str]:
        """Call Gemini and parse the JSON array response."""
        try:
            client = self._get_client()
            # Gemini SDK is synchronous — run in executor to stay non-blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.generate_content(text),
            )
            raw = response.text.strip()

            # Strip markdown code fences if the model wrapped the output
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            skills = json.loads(raw)
            if not isinstance(skills, list):
                raise ValueError("LLM did not return a JSON array")

            # Normalize and deduplicate
            return list({s.strip() for s in skills if isinstance(s, str) and s.strip()})

        except Exception as exc:
            log.warning(f"SkillExtractor LLM call failed: {exc}")
            return []
