"""
app/insights.py — Public, aggregate-only numbers for the Insights page.

Everything here is a COUNT over PUBLIC columns (tags, city, dates) or over the synthetic external
catalog, plus counts of blocked attempts BY REASON from the audit log. No row is returned, no private
or organiser-only column is read, and no query text from the log is ever exposed.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.external_catalog import _load as load_external_catalog
from app.permissions import MODEL_MAP

_CACHE_TTL = 60.0
_cache: Dict[str, Any] = {"at": 0.0, "value": None}
_lock = threading.Lock()


def _entity_counts(db: Session) -> Dict[str, int]:
    return {name: db.execute(select(func.count()).select_from(model)).scalar_one() for name, model in MODEL_MAP.items()}


def _upcoming(db: Session, today: date) -> Dict[str, int]:
    ev, hk = MODEL_MAP["event"], MODEL_MAP["hackathon"]
    soon = today + timedelta(days=30)
    return {
        "events_next_30_days": db.execute(select(func.count()).where(ev.event_date >= today, ev.event_date <= soon)).scalar_one(),
        "hackathons_next_30_days": db.execute(select(func.count()).where(hk.start_date >= today, hk.start_date <= soon)).scalar_one(),
        "upcoming_events": db.execute(select(func.count()).where(ev.event_date >= today)).scalar_one(),
        "upcoming_hackathons": db.execute(select(func.count()).where(hk.start_date >= today)).scalar_one(),
    }


def _upcoming_by_city(db: Session, today: date):
    """Where is something happening soon: upcoming events + hackathons per city (public columns only)."""
    ev, hk = MODEL_MAP["event"], MODEL_MAP["hackathon"]
    counts = Counter()
    for model, col in ((ev, ev.event_date), (hk, hk.start_date)):
        for city, n in db.execute(select(model.city, func.count()).where(col >= today).group_by(model.city)):
            counts[city] += n
    return [{"name": k, "count": v} for k, v in counts.most_common()]


def _technologies_and_cities(db: Session) -> Dict[str, Any]:
    tech, cities = Counter(), Counter()
    for name, model in MODEL_MAP.items():
        cols = [c for c in ("tags", "city") if hasattr(model, c)]
        for row in db.execute(select(*[getattr(model, c) for c in cols])):
            values = dict(zip(cols, row))
            for t in (values.get("tags") or "").split(","):
                if t.strip():
                    tech[t.strip()] += 1
            if values.get("city"):
                cities[values["city"]] += 1
    return {
        "top_technologies": [{"name": k, "count": v} for k, v in tech.most_common(12)],
        "cities": [{"name": k, "count": v} for k, v in cities.most_common()],
    }


def _external() -> Dict[str, Any]:
    rows = load_external_catalog()
    by_platform = Counter(r["source_platform"] for r in rows)
    by_entity = Counter(r["entity_type"] for r in rows)
    return {
        "total": len(rows),
        "platforms": [{"name": k, "count": v} for k, v in by_platform.most_common()],
        "entities": [{"name": k, "count": v} for k, v in by_entity.most_common()],
    }


def _safety() -> Dict[str, Any]:
    """Blocked-attempt counts by reason. The raw query text in the log is never read out."""
    by_reason, last_24h, total = Counter(), 0, 0
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    path = config.LOG_BLOCKED_ATTEMPTS_PATH
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict):
                    continue  # a malformed line must never break the page
                reason = str(entry.get("reason", "unknown"))
                if reason == "fields_dropped":
                    continue  # not a block: some values were simply not in the allow-lists
                total += 1
                by_reason[reason] += 1
                try:
                    if datetime.fromisoformat(entry["timestamp"]) >= since:
                        last_24h += 1
                except (KeyError, ValueError, TypeError):
                    pass
    labels = {
        "suspicious_pattern_in_query": "Injection / private-data request",
        "could_not_determine_entity_type": "Unclear query",
        "web_enrich_blocked": "Blocked web lookup",
    }
    return {
        "blocked_total": total,
        "blocked_last_24h": last_24h,
        "by_reason": [{"name": labels.get(k, k.replace("_", " ")), "count": v} for k, v in by_reason.most_common()],
    }


def compute_insights(db: Session, runtime: Dict[str, Any]) -> Dict[str, Any]:
    """Cached for 60 s: the page is cheap to refresh and the numbers change slowly."""
    now = time.monotonic()
    with _lock:
        if _cache["value"] is not None and now - _cache["at"] < _CACHE_TTL:
            return {**_cache["value"], "runtime": runtime}
    today = date.today()
    value = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entities": _entity_counts(db),
        "upcoming": _upcoming(db, today),
        "upcoming_by_city": _upcoming_by_city(db, today),
        **_technologies_and_cities(db),
        "external": _external(),
        "safety": _safety(),
    }
    with _lock:
        _cache.update(at=now, value=value)
    return {**value, "runtime": runtime}
