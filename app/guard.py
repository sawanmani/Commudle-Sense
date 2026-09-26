"""
app/guard.py — Stage 0: raw-query guard. Runs BEFORE any LLM call or web request.

Normalises the query (Unicode NFKC, zero-width/control chars removed, whitespace collapsed) so
homoglyph / invisible-character tricks can't dodge the patterns, then scans it with the
validation regexes plus extra exfiltration patterns (incl. Hindi/Hinglish). A hit blocks the
whole request — nothing reaches the model, the database or DuckDuckGo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.validation import _SUSPICIOUS_RE

MAX_QUERY_LEN = 500

_EXTRA = re.compile(
    "|".join([
        # asking for private contact / credential data
        r"\b(e-?mails?|phones?|mobile|whatsapp|contact)\s*(numbers?|ids?|addresses|address|list|column|dump)",
        r"\b(show|give|list|dump|reveal|print|get|dikha\w*|bata\w*)\b.{0,40}\b(e-?mails?|phones?|mobile|whatsapp|passwords?)\b",
        r"\b(return|select|include)\b.{0,40}\b(e-?mail|phone|password)\s+column",
        # private / organiser-only artefacts
        r"\b(attendance|rsvps?|applicants?|registrations?|judging|analytics|drafts?)\b.{0,30}\b(list|log|show|dump|reveal|notes?|content|data)\b",
        r"\b(list|log|show|dump|reveal|give|export)\b.{0,30}\b(attendance|rsvps?|applicants?|judging|analytics)\b",
        r"organi[sz]er\s+(analytics|only)",
        # Hindi / Devanagari
        r"(फोन|फ़ोन|मोबाइल)\s*(नंबर|नम्बर)",
        r"ई-?मेल|पासवर्ड|निजी\s*(डेटा|जानकारी)",
        # stacked / obfuscated SQL
        r";\s*(drop|delete|select|insert|update|truncate)\b",
        r"%'\s*or\s*'",
        r"/\*.*\*/",
    ]),
    re.IGNORECASE | re.DOTALL,
)

_INVISIBLE = re.compile(r"[​-\u200F\u202A-\u202E⁠﻿\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_query(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw or "")
    text = _INVISIBLE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_QUERY_LEN]


def check_raw_query(raw: str) -> Optional[str]:
    """Return a block reason, or None if the query may proceed."""
    text = normalize_query(raw)
    if not text:
        return "empty_query"
    if _SUSPICIOUS_RE.search(text) or _EXTRA.search(text):
        return "suspicious_pattern_in_query"
    return None
