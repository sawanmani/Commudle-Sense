"""
app/autocomplete.py — Bonus: safe pool suggestions.

Suggestions come ONLY from a pre-built pool of template strings crossed with
allow-list vocabulary. No LLM call per keystroke. Raw user input is never returned.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional

from app.config import (
    KNOWN_TECHNOLOGIES,
    KNOWN_CITIES,
    KNOWN_ROLES,
    KNOWN_CONTENT_TYPES,
)

# ── Templates ──────────────────────────────────────────────────────────────────
_TEMPLATES = [
    "{tech} events",
    "{tech} events in {city}",
    "{tech} communities",
    "{tech} communities in {city}",
    "{tech} speakers",
    "{tech} speakers in {city}",
    "{tech} hackathons",
    "{tech} hackathons in {city}",
    "{tech} jobs",
    "{tech} jobs in {city}",
    "{tech} {content} in {city}",
    "{tech} {content}",
    "{role}s in {city}",
    "{role}s near me",
    "{content} on {tech}",
    "{content} on {tech} in {city}",
    "{tech} builds",
    "{tech} labs",
    "{tech} labs in {city}",
]

# ── Build the safe pool ───────────────────────────────────────────────────────
_pool: List[str] = []

for tpl in _TEMPLATES:
    needs_tech = "{tech}" in tpl
    needs_city = "{city}" in tpl
    needs_role = "{role}" in tpl
    needs_content = "{content}" in tpl

    techs = KNOWN_TECHNOLOGIES if needs_tech else [""]
    cities = KNOWN_CITIES[:8] if needs_city else [""]
    roles = KNOWN_ROLES if needs_role else [""]
    contents = KNOWN_CONTENT_TYPES if needs_content else [""]

    for tech in techs:
        for city in cities:
            for role in roles:
                for content in contents:
                    s = tpl.format(
                        tech=tech, city=city, role=role, content=content
                    ).strip()
                    if s:
                        _pool.append(s)

# Deduplicate
_pool = sorted(set(_pool))

# ── Popularity counter (updated after successful validated queries) ────────────
_popularity: Counter = Counter()


def record_successful_query(cleaned_query: str) -> None:
    """Call AFTER validation + execution with the cleaned query string."""
    lowered = cleaned_query.lower().strip()
    if lowered:
        _popularity[lowered] += 1


def suggest(prefix: str, city: Optional[str] = None, limit: int = 6) -> List[str]:
    """Return up to `limit` suggestions from the safe pool. Min length 2."""
    if not prefix or len(prefix.strip()) < 2:
        return []

    prefix_lower = prefix.strip().lower()
    tokens = prefix_lower.split()

    scored: List[tuple] = []

    for s in _pool:
        s_lower = s.lower()

        # ── Tier 0: contiguous prefix match ────────────────────────────────
        if s_lower.startswith(prefix_lower):
            tier = 0
        # ── Tier 1: every token is a word-prefix ───────────────────────────
        elif all(
            any(w.startswith(t) for w in s_lower.split()) for t in tokens
        ):
            tier = 1
        # ── Tier 2: every token appears somewhere ──────────────────────────
        elif all(t in s_lower for t in tokens):
            tier = 2
        else:
            continue

        # ── Locality boost ─────────────────────────────────────────────────
        locality = 0
        if city and city.lower() in s_lower:
            locality = 2
        elif "near me" in s_lower:
            locality = 1

        pop = _popularity.get(s_lower, 0)
        scored.append((tier, -locality, -pop, len(s), s))

    scored.sort()
    return [item[-1] for item in scored[:limit]]
