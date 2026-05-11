"""
Scoring logic for the AI Job Vulnerability Calculator.
Combines occupation-level data with state-level modifiers to produce
a personalized vulnerability score and a 5-year trajectory.
"""

import math
import re
from typing import List, Dict, Any


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def search_occupations(occupations: list, query: str, limit: int = 20) -> list:
    """
    Search occupations by title + aliases. Returns ranked list.
    Ranking: exact title > exact alias > title contains query > alias contains > token overlap.
    """
    q = _norm(query)
    if not q:
        return []

    results = []
    q_tokens = set(q.split())

    for o in occupations:
        title = _norm(o["title"])
        aliases = [_norm(a) for a in o.get("aliases", [])]

        score = 0
        if title == q:
            score = 1000
        elif q in aliases:
            score = 900
        elif title.startswith(q):
            score = 700
        elif any(a.startswith(q) for a in aliases):
            score = 650
        elif q in title:
            score = 500
        elif any(q in a for a in aliases):
            score = 450
        else:
            # token-overlap fallback
            t_tokens = set(title.split())
            a_tokens = set(t for a in aliases for t in a.split())
            overlap = len(q_tokens & (t_tokens | a_tokens))
            if overlap > 0:
                score = 200 + overlap * 50

        if score > 0:
            results.append((score, o))

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]


def score_for(occ: dict, state: dict, nat_avg: float) -> Dict[str, Any]:
    """
    Compute the personalized score for occupation + state.
    The state pct acts as a soft modifier: states above the national average
    nudge the score up; states below nudge it down.
    """
    base = occ["job_loss_pct"]  # base occupational %
    state_pct = state["p"]

    # State modifier: (state_pct / nat_avg) - 1
    # E.g. DC=11.3 / 6.16 = 1.83 -> +83% adjustment, scaled down by alpha
    alpha = 0.20  # max ±20% adjustment from state mix
    state_modifier = ((state_pct - nat_avg) / nat_avg) * alpha
    personalized = base * (1 + state_modifier)
    personalized = max(0.5, min(95.0, personalized))  # clamp sane bounds

    # Build 5-year trajectory using logistic adoption curve
    # f(t) = ceil / (1 + exp(-k*(t - half)))
    # half is set so that f(today) ≈ personalized/2 (we're early on the curve)
    ceiling = min(100, base * 1.5 + 15)  # speculative max saturation by 2045
    half_year = 2026 + max(2, int((50 / max(base, 1)) * 1.6))  # heuristic
    k = 0.30 + (base / 200)  # steeper for higher-vuln jobs

    trajectory = []
    for offset in range(0, 6):
        yr = 2026 + offset
        val = ceiling / (1 + math.exp(-k * (yr - half_year)))
        trajectory.append({"year": yr, "pct": round(val, 1)})

    # Severity bucket
    if personalized >= 40:
        severity = "critical"
        severity_label = "Acute — your role is among the most exposed in the country."
    elif personalized >= 25:
        severity = "high"
        severity_label = "Elevated — significant restructuring is likely in 2–5 years."
    elif personalized >= 12:
        severity = "moderate"
        severity_label = "Moderate — some tasks will shift, full displacement unlikely soon."
    elif personalized >= 5:
        severity = "low"
        severity_label = "Low — mostly insulated, but augmentation will reshape the work."
    else:
        severity = "minimal"
        severity_label = "Minimal — your role's tasks are largely outside current AI capability."

    return {
        "base_pct":           round(base, 1),
        "vulnerability_pct":  round(personalized, 1),
        "national_avg_pct":   nat_avg,
        "state_pct":          state_pct,
        "rank":               occ["rank"],
        "total":              occ["total"],
        "category":           occ["category"],
        "physicality":        occ["physicality"],
        "exposure":           occ.get("exposure", 0),
        "augmentation":       occ.get("augmentation", 0),
        "adjacent_safer":     occ.get("adjacent_safer", []),
        "at_risk_tasks":      occ.get("at_risk_tasks", []),
        "skills_to_learn":    occ.get("skills_to_learn", []),
        "trajectory":         trajectory,
        "severity":           severity,
        "severity_label":     severity_label,
        "half_saturation_yr": half_year,
        "ceiling":            round(ceiling, 1),
    }


def rank_among(occupations: list, target: dict) -> int:
    """Return 1-indexed rank of target occupation."""
    return target.get("rank", 1)
