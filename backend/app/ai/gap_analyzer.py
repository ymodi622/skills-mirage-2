"""
gap_analyzer.py — Pure Python gap computation (no LLM, no DB).

Takes the user's normalized skill list and a pre-computed market frequency
list, then buckets skills into strengths / hard gaps / nice-to-have gaps
and produces a match score.
"""

from __future__ import annotations


class GapAnalyzer:

    def analyze_gap(
        self,
        user_skills: list[str],
        market_skills_freq: list[dict],
        required_threshold: float = 0.30,
        nice_to_have_threshold: float = 0.15,
    ) -> dict:
        """
        Compare user skills against market demand.

        Parameters
        ----------
        user_skills           : normalized list of the user's skill names
        market_skills_freq    : list of {"skill": str, "frequency": float}
                                sorted by frequency descending
        required_threshold    : skills with freq >= this are "required gaps"
        nice_to_have_threshold: skills with freq in [this, required) are "nice-to-have"

        Returns
        -------
        {
            "strengths":     list[str],   # user has it AND market wants it (freq >= required)
            "gaps":          list[str],   # market wants it (freq >= required), user lacks it
            "nice_to_have":  list[str],   # market prefers it (freq in range), user lacks it
            "rare":          list[str],   # user has it but market rarely asks for it
            "match_score":   float,       # 0-100, % of required market skills the user covers
        }
        """
        # Lowercase set for O(1) membership checks
        user_set = {s.lower() for s in user_skills}

        # Split market skills by threshold band
        required_market  = [e for e in market_skills_freq if e["frequency"] >= required_threshold]
        preferred_market = [
            e for e in market_skills_freq
            if nice_to_have_threshold <= e["frequency"] < required_threshold
        ]

        # -- Strengths: user has the skill AND it's in high demand
        strengths = [
            e["skill"] for e in required_market
            if e["skill"].lower() in user_set
        ]

        # -- Hard gaps: high-demand skill the user is missing
        gaps = [
            e["skill"] for e in required_market
            if e["skill"].lower() not in user_set
        ]

        # -- Nice-to-have gaps: medium-demand skill the user is missing
        nice_to_have = [
            e["skill"] for e in preferred_market
            if e["skill"].lower() not in user_set
        ]

        # -- Rare: user skills that barely appear in the market
        market_all_lower = {e["skill"].lower() for e in market_skills_freq}
        rare = [s for s in user_skills if s.lower() not in market_all_lower]

        # -- Match score: % of required market skills the user already covers
        match_score = (
            round(len(strengths) / len(required_market) * 100, 1)
            if required_market else 0.0
        )

        summary = {
            "strengths_count": len(strengths),
            "hard_gaps_count": len(gaps),
            "nice_to_have_count": len(nice_to_have),
            "rare_skills_count": len(rare),
            "total_market_skills": len(market_skills_freq),
            "match_percentage": f"{match_score}%",
        }

        return {
            "strengths": strengths,
            "gaps": gaps,
            "nice_to_have": nice_to_have,
            "rare": rare,
            "match_score": match_score,
            "summary": summary,
        }

