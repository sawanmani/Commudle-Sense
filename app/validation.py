"""
app/validation.py — Stage 2: Allow-list validation + injection stripping.

The REAL defense layer. Every field from the LLM output is validated against
closed allow-lists using fuzzy matching. Suspicious patterns (SQLi, prompt
injection, role escalation, data exfiltration, XSS) are detected via regex
and cause the field to be DROPPED (fail-closed). This module NEVER raises.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from rapidfuzz import fuzz, process as rfprocess

from app.config import (
    KNOWN_TECHNOLOGIES,
    KNOWN_CITIES,
    KNOWN_ROLES,
    KNOWN_ENTITY_TYPES,
    KNOWN_CONTENT_TYPES,
)
from app.schemas import SearchIntent, EntityType

# ── Suspicious pattern groups (~48 patterns) ───────────────────────────────────
_PROMPT_INJECTION = [
    r"ignore\s+(previous|all|above|prior)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(all|previous|prior|above)",
    r"system\s*:",
    r"new\s+instructions?\s*:",
    r"you\s+are\s+now",
    r"pretend\s+to\s+be",
    r"act\s+as\s+(the\s+)?(database|admin|system|root)",
    r"reveal\s+(the\s+)?system\s+prompt",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"DAN\s+mode",
]

_SQL_INJECTION = [
    r"drop\s+table",
    r"select\s+.+\s+from\s+",
    r"delete\s+from",
    r"union\s+select",
    r"insert\s+into",
    r"update\s+.+\s+set\s+",
    r"truncate\s+",
    r"or\s+1\s*=\s*1",
    r"information_schema",
    r"sleep\s*\(",
    r"benchmark\s*\(",
    r"load_file\s*\(",
    r"into\s+outfile",
    r"xp_cmdshell",
    r";\s*--",
    r"'\s*;\s*",
]

_ROLE_ESCALATION = [
    r"as\s+an?\s+(organiser|admin|administrator|root)",
    r"i\s+am\s+(the\s+)?admin",
    r"grant\s+me",
    r"escalate\s+(my\s+)?(privileges?|role|access|permissions?)",
]

_DATA_EXFILTRATION = [
    r"show\s+me\s+all\s+(emails?|phones?|rsvp|attendance)",
    r"dump\s+(the\s+)?table",
    r"export\s+(all\s+)?data",
    r"raw\s+sql",
    r"api[_\s]?key",
    r"secret",
    r"password",
    r"token",
    r"email\s+(list|dump)",
    r"phone\s+(list|dump)",
    r"registrations?\s+(list|dump)",
    r"rsvp\s+(list|dump)",
    r"form\s+responses?",
    r"private\s+channel",
    r"private\s+notes?",
    r"internal\s+notes?",
    r"organiser\s+notes?",
    r"draft\s+content",
]

_XSS = [
    r"<\s*script",
    r"onerror\s*=",
    r"onload\s*=",
    r"javascript\s*:",
]

_ALL_PATTERNS = _PROMPT_INJECTION + _SQL_INJECTION + _ROLE_ESCALATION + _DATA_EXFILTRATION + _XSS

_SUSPICIOUS_RE = re.compile("|".join(_ALL_PATTERNS), re.IGNORECASE)


def _fuzzy_match_or_none(
    value: Optional[str],
    allowed: List[str],
    threshold: int = 80,
) -> Optional[str]:
    """Fuzzy-match a value to an allow-list. Returns None if suspicious or no match."""
    if value is None:
        return None
    value_str = str(value).strip()
    if not value_str:
        return None
    # Suspicious? Drop immediately.
    if _SUSPICIOUS_RE.search(value_str):
        return None
    result = rfprocess.extractOne(
        value_str.lower(), allowed, scorer=fuzz.WRatio
    )
    if result is None:
        return None
    match, score, _ = result
    return match if score >= threshold else None


def _clean_free_text(text: Optional[str]) -> Optional[str]:
    """Strip control chars; keep word chars, whitespace, Devanagari, basic punctuation. Cap 300."""
    if text is None:
        return None
    # Keep: word chars, whitespace, Devanagari range, .,!?-
    cleaned = re.sub(r"[^\w\s\u0900-\u097F.,!?\-]", "", text)
    cleaned = cleaned.strip()[:300]
    return cleaned if cleaned else None


def validate_intent(intent: SearchIntent) -> Tuple[SearchIntent, List[str]]:
    """Validate and sanitize a SearchIntent against allow-lists.

    Returns (cleaned_intent, list_of_dropped_field_names). Never raises.
    """
    dropped: List[str] = []

    # ── entity_type ────────────────────────────────────────────────────────
    if intent.entity_type.value not in (KNOWN_ENTITY_TYPES + ["unknown"]):
        dropped.append(f"entity_type:{intent.entity_type.value}")
        intent.entity_type = EntityType.unknown

    # ── technologies ───────────────────────────────────────────────────────
    clean_techs: List[str] = []
    for t in intent.technologies:
        matched = _fuzzy_match_or_none(t, KNOWN_TECHNOLOGIES)
        if matched:
            clean_techs.append(matched)
        else:
            dropped.append(f"technology:{t}")
    intent.technologies = clean_techs

    # ── location ───────────────────────────────────────────────────────────
    matched_loc = _fuzzy_match_or_none(intent.location, KNOWN_CITIES)
    if intent.location and not matched_loc:
        dropped.append(f"location:{intent.location}")
    intent.location = matched_loc

    # ── role ───────────────────────────────────────────────────────────────
    matched_role = _fuzzy_match_or_none(intent.role, KNOWN_ROLES)
    if intent.role and not matched_role:
        dropped.append(f"role:{intent.role}")
    intent.role = matched_role

    # ── content_type ───────────────────────────────────────────────────────
    matched_ct = _fuzzy_match_or_none(intent.content_type, KNOWN_CONTENT_TYPES)
    if intent.content_type and not matched_ct:
        dropped.append(f"content_type:{intent.content_type}")
    intent.content_type = matched_ct

    # ── free_text_remainder ────────────────────────────────────────────────
    intent.free_text_remainder = _clean_free_text(intent.free_text_remainder)

    return intent, dropped
