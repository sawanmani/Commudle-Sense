"""
app/ranking.py — Stage 5: Hybrid score = semantic + recency.

Lazy-loads the embedding model. Degrades gracefully if sentence-transformers
or torch are missing (returns zero vectors).
"""

from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app import config

EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # must match Vector(384) in models.py

# ── Lazy singleton embedder ───────────────────────────────────────────────────
# States: None = not tried yet, "loading" = a thread is loading it, False = unavailable, else the model.
_embedder = None
_embedder_lock = threading.Lock()


def _load_embedder():
    global _embedder
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBED_MODEL_NAME)
    except Exception:
        model = False
    with _embedder_lock:
        _embedder = model


def get_embedder(block: bool = True):
    """The embedding model, or None if unavailable.

    With block=False (the request path) a model that is still loading returns None immediately, so the
    first searches after start-up use filters + recency instead of waiting ~1 min for the model.
    """
    global _embedder
    if not config.ENABLE_EMBEDDINGS:
        return None
    with _embedder_lock:
        state = _embedder
        if state is None:
            _embedder = "loading"
    if state is None:
        if not block:
            threading.Thread(target=_load_embedder, daemon=True, name="embedder-load").start()
            return None
        _load_embedder()
        return _embedder or None
    if state == "loading":
        if not block:
            return None
        while _embedder == "loading":
            time.sleep(0.05)
        return _embedder or None
    return state or None


def warm_up() -> None:
    """Start loading the model in the background (called at API start-up)."""
    get_embedder(block=False)


def embedder_status() -> str:
    if not config.ENABLE_EMBEDDINGS:
        return "disabled"
    if hasattr(_embedder, "encode"):
        return "ready"
    return {None: "not loaded", "loading": "loading"}.get(_embedder, "unavailable")


def embed_text(text: Optional[str], block: bool = True) -> List[float]:
    """Embed text into a normalized vector. Returns zeros if empty or model unavailable."""
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM
    embedder = get_embedder(block=block)
    if embedder is None:
        return [0.0] * EMBEDDING_DIM
    try:
        vec = embedder.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception:
        return [0.0] * EMBEDDING_DIM


def recency_score(
    created_at: Any,
    half_life_days: float = 90.0,
) -> float:
    """Compute a recency score in [0, 1]. None → 0.5, future → 1.0."""
    if created_at is None:
        return 0.5

    # Parse string dates if needed
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            return 0.5

    # Convert date to datetime for comparison
    if isinstance(created_at, date) and not isinstance(created_at, datetime):
        created_at = datetime.combine(created_at, datetime.min.time())

    # Assume UTC for naive datetimes
    if created_at.tzinfo is None:
        now = datetime.now(tz=None)
    else:
        now = datetime.now(timezone.utc)

    age_days = (now - created_at).total_seconds() / 86400.0

    # Clamp: future dates → 1.0 (prevent blowing score above 1)
    if age_days <= 0:
        return 1.0

    return math.exp(-age_days / half_life_days)


def upcoming_score(when: Any, half_life_days: float = 45.0) -> float:
    """Soonest future date scores highest; past dates get a small floor. None -> 0.5."""
    if when is None:
        return 0.5
    try:
        d = date.fromisoformat(when[:10]) if isinstance(when, str) else (when.date() if isinstance(when, datetime) else when)
    except (ValueError, TypeError):
        return 0.5
    days = (d - date.today()).days
    return 0.1 if days < 0 else math.exp(-days / half_life_days)


def _as_date(when: Any) -> Optional[date]:
    try:
        if isinstance(when, str):
            return date.fromisoformat(when[:10])
        return when.date() if isinstance(when, datetime) else when
    except (ValueError, TypeError, AttributeError):
        return None


def timeliness_score(when: Any, today: Optional[date] = None) -> float:
    """For dated things people attend (events, hackathons): every upcoming item outranks every past one.

    today .. +1 year  -> 1.0 .. ~0.45 (sooner is better);  past -> <= 0.3, fading over months;  unknown -> 0.4.
    """
    d = _as_date(when)
    if d is None:
        return 0.4
    days = (d - (today or date.today())).days
    if days >= 0:
        return 0.45 + 0.55 * math.exp(-days / 120.0)
    return 0.3 * math.exp(days / 180.0)


def effective_weights(rows: List[Dict[str, Any]], w_sem: float, w_recency: float, w_activity: float):
    """Drop signals the rows don't have (no similarity / no dates / no activity) and renormalise the rest to sum 1."""
    w = {
        "sem": w_sem if any(r.get("similarity") is not None for r in rows) else 0.0,
        "rec": w_recency if any(r.get("_date_value") is not None for r in rows) else 0.0,
        "act": w_activity if any(r.get("_activity") is not None for r in rows) else 0.0,
    }
    total = sum(w.values())
    if total <= 0:
        return 0.0, 1.0, 0.0  # nothing to rank on: neutral time score for all
    return w["sem"] / total, w["rec"] / total, w["act"] / total


def rank_results(
    rows: List[Dict[str, Any]],
    query_embedding: Optional[List[float]] = None,
    w_sem: float = 0.6,
    w_recency: float = 0.4,
    sort: str = "relevance",
    w_activity: float = 0.0,
    time_bound: bool = False,
) -> List[Dict[str, Any]]:
    """Re-rank rows: score = w_sem*similarity + w_recency*time_signal + w_activity*activity, in [0, 1].

    time_signal is timeliness (upcoming first) for events/hackathons, nearness for sort=upcoming, else recency.
    When no row has a similarity (no embedding model / entity without vectors) the semantic weight is
    shared out to the other signals, so scores still use the full 0..1 range. Pure re-ranking, no DB access.
    """
    w_sem, w_recency, w_activity = effective_weights(rows, w_sem, w_recency, w_activity)
    # Activity (talks given / member count) normalised within the result set; 0 weight = off.
    acts = [r.get("_activity") for r in rows if r.get("_activity") is not None]
    top = max(acts) if acts else 0
    for r in rows:
        sim = max(0.0, r.get("similarity") or 0.0)  # handle None (§15.5)
        when = r.get("_date_value")
        if sort == "upcoming":
            rec = upcoming_score(when)
        elif time_bound:
            rec = timeliness_score(when)
        else:
            rec = recency_score(when)
        act = (math.log1p(r["_activity"]) / math.log1p(top)) if (w_activity and top and r.get("_activity") is not None) else 0.0
        r["score"] = round(w_sem * sim + w_recency * rec + w_activity * act, 4)

    return sorted(rows, key=lambda r: r["score"], reverse=True)
