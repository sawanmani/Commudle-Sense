"""
app/ranking.py — Stage 5: Hybrid score = semantic + recency.

Lazy-loads the embedding model. Degrades gracefully if sentence-transformers
or torch are missing (returns zero vectors).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # must match Vector(384) in models.py

# ── Lazy singleton embedder ───────────────────────────────────────────────────
_embedder = None


def get_embedder():
    """Lazily load the sentence-transformers model. Returns None if unavailable."""
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBED_MODEL_NAME)
        return _embedder
    except Exception:
        return None


def embed_text(text: Optional[str]) -> List[float]:
    """Embed text into a normalized vector. Returns zeros if empty or model unavailable."""
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM
    embedder = get_embedder()
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


def rank_results(
    rows: List[Dict[str, Any]],
    query_embedding: Optional[List[float]] = None,
    w_sem: float = 0.6,
    w_recency: float = 0.4,
) -> List[Dict[str, Any]]:
    """Re-rank rows by hybrid score = w_sem * similarity + w_recency * recency.

    Pure re-ranking, no DB access. Handles None similarity gracefully.
    """
    for r in rows:
        sim = r.get("similarity") or 0.0  # handle None (§15.5)
        rec = recency_score(r.get("_date_value"))
        r["score"] = round(w_sem * sim + w_recency * rec, 4)

    return sorted(rows, key=lambda r: r["score"], reverse=True)
