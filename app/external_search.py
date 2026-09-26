"""
app/external_search.py — Bonus: DuckDuckGo web enrichment.

Results are NEVER fed back to the LLM, never build a query, have no DB access.
The UI must label them as external/unverified and render URLs as non-clickable text.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.validation import redact_suspicious
from app.config import (
    ENABLE_WEB_SEARCH,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_TIMEOUT_SECONDS,
)


def safe_web_search(query: str) -> List[Dict[str, Any]]:
    """Perform a safe DuckDuckGo web search. Fail-closed: returns [] on any error."""
    if not ENABLE_WEB_SEARCH:
        return []

    # Cap query length
    query = query[:200]

    try:
        try:
            from ddgs import DDGS  # current package name
        except ImportError:  # pragma: no cover - legacy name (returns nothing on recent versions)
            from duckduckgo_search import DDGS
        raw = DDGS(timeout=WEB_SEARCH_TIMEOUT_SECONDS).text(query, max_results=WEB_SEARCH_MAX_RESULTS) or []
        # Web pages are untrusted: redact injection-looking text like any other stored content.
        return [{
            "title": redact_suspicious(r.get("title", ""), 200),
            "snippet": redact_suspicious(r.get("body", ""), 300),
            "url": r.get("href", ""),
            "source": "external_web",
        } for r in raw]
    except Exception:
        return []
