"""
app/external_catalog.py — "Other platforms" search over seed/external_platforms_dataset.json.

Runs on the SAME validated SearchIntent as the local search (allow-listed tech/city/entity),
in memory, with no DB and no LLM access. Everything returned is treated as untrusted content:
  * text fields are scanned with the validation regexes and redacted if suspicious
  * redirect URLs must be https and on an allow-listed platform host, else dropped
Matching relaxes step by step (exact -> any city -> any tech) so the section is rarely empty;
each hit says which level matched.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.schemas import SearchIntent
from app.validation import _SUSPICIOUS_RE, redact_suspicious  # noqa: F401  (re-exported for tests)

DATASET_PATH = os.getenv(
    "EXTERNAL_DATASET_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "external_platforms_dataset.json"),
)

ALLOWED_HOSTS = {
    "devfolio.co", "devpost.com", "unstop.com", "www.hackerearth.com", "hack2skill.com",
    "dorahacks.io", "www.commudle.com", "lu.ma",
}
REDACTED = "[content removed by safety filter]"
_STATUS_RANK = {"ongoing": 3, "upcoming": 3, "open": 2, "active": 2, "showcase": 1, "completed": 0}

_catalog: Optional[List[Dict[str, Any]]] = None


def _load() -> List[Dict[str, Any]]:
    global _catalog
    if _catalog is None:
        try:
            with open(DATASET_PATH, encoding="utf-8") as f:
                _catalog = json.load(f)
        except Exception:
            _catalog = []  # fail closed: no external results
    return _catalog


def _safe_url(url: Optional[str]) -> Optional[str]:
    try:
        p = urlparse(url or "")
    except ValueError:
        return None
    return url if p.scheme == "https" and p.hostname in ALLOWED_HOSTS else None


def _safe_text(text: Optional[str], limit: int) -> str:
    return redact_suspicious(text, limit, REDACTED)


def _proximity(row: Dict[str, Any]) -> float:
    """1.0 for dates near today, decaying with distance; 0.5 when the row has no date."""
    raw = row.get("start_date")
    try:
        d = date.fromisoformat(raw) if raw else None
    except ValueError:
        d = None
    if d is None:
        return 0.5
    return 1.0 / (1.0 + abs((d - date.today()).days) / 90.0)


def _in_range(row: Dict[str, Any], intent: SearchIntent) -> bool:
    if not intent.date_range:
        return True
    try:
        d = date.fromisoformat(row.get("start_date") or "")
    except ValueError:
        return True
    for bound, cmp in ((intent.date_range.from_date, lambda x, b: x >= b), (intent.date_range.to_date, lambda x, b: x <= b)):
        if bound:
            try:
                if not cmp(d, datetime.strptime(bound, "%Y-%m-%d").date()):
                    return False
            except ValueError:
                pass
    return True


def search_external(intent: SearchIntent, limit: int = 12) -> List[Dict[str, Any]]:
    """Return up to `limit` sanitized external hits for a VALIDATED intent."""
    entity = intent.entity_type.value
    if entity == "unknown":
        return []
    pool = [r for r in _load() if r["entity_type"] == entity and _in_range(r, intent)]
    techs, city = set(intent.technologies), intent.location

    def tech_ok(r):
        return not techs or bool(techs & set(r["technologies"]))

    def city_ok(r):
        return not city or r["city"] == city or (r["city"] == "remote")

    levels = [
        ("exact", [r for r in pool if tech_ok(r) and city_ok(r)]),
        ("relaxed_city", [r for r in pool if tech_ok(r)]),
        ("relaxed_tech", [r for r in pool if city_ok(r)]),
    ]
    picked, seen = [], set()
    for level, rows in levels:
        rows = sorted(rows, key=lambda r: (_STATUS_RANK.get(r["status"], 0), _proximity(r)), reverse=True)
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            picked.append((level, r))
            if len(picked) >= limit:
                break
        if len(picked) >= limit:
            break

    out = []
    for level, r in picked:
        url = _safe_url(r.get("redirect_url"))
        if url is None:
            continue
        if level == "exact" and city and r["city"] == "remote" and city != "remote":
            level = "online"  # not in the city you asked for, but you can join from anywhere
        exact_bonus = {"exact": 1.0, "online": 0.85, "relaxed_city": 0.6, "relaxed_tech": 0.4}[level]
        out.append({
            "id": r["id"],
            "source_platform": r["source_platform"],
            "entity_type": r["entity_type"],
            "title": _safe_text(r["title"], 200),
            "snippet": _safe_text(r["description"], 300),
            "city": r["city"],
            "mode": r.get("mode"),
            "start_date": r.get("start_date"),
            "status": r.get("status"),
            "redirect_url": url,
            "match_level": level,
            "is_synthetic": bool(r.get("is_synthetic", True)),
            "score": round(0.7 * exact_bonus + 0.3 * _proximity(r), 4),
        })
    return sorted(out, key=lambda x: x["score"], reverse=True)
