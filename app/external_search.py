"""
app/external_search.py — Bonus: DuckDuckGo web enrichment.

Results are NEVER fed back to the LLM, never build a query, have no DB access.
The UI must label them as external/unverified and render URLs as non-clickable text.
"""

from __future__ import annotations

from typing import Any, Dict, List

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
        from duckduckgo_search import DDGS
        with DDGS(timeout=WEB_SEARCH_TIMEOUT_SECONDS) as ddgs:
            raw = ddgs.text(query, max_results=WEB_SEARCH_MAX_RESULTS)
            results = []
            for r in raw:
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                    "source": "external_web",
                })
            return results
    except Exception:
        return []
