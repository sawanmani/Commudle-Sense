"""
tests/test_ranking.py — Deterministic ranking tests (no DB/LLM).
"""

from datetime import datetime, timedelta
from app.ranking import recency_score, rank_results, EMBEDDING_DIM


class TestRecencyScore:
    """Verify recency scoring behavior."""

    def test_none_returns_neutral(self):
        assert recency_score(None) == 0.5

    def test_today_returns_high(self):
        score = recency_score(datetime.now())
        assert score > 0.95

    def test_old_date_returns_low(self):
        old = datetime.now() - timedelta(days=365)
        score = recency_score(old)
        assert score < 0.1

    def test_future_clamped_to_one(self):
        future = datetime.now() + timedelta(days=30)
        score = recency_score(future)
        assert score == 1.0

    def test_string_date(self):
        score = recency_score(datetime.now().isoformat())
        assert 0 < score <= 1.0


class TestRankResults:
    """Verify hybrid ranking."""

    def test_empty_rows(self):
        assert rank_results([], None) == []

    def test_null_similarity_handled(self):
        rows = [
            {"id": 1, "similarity": None, "_date_value": None},
            {"id": 2, "similarity": 0.5, "_date_value": None},
        ]
        ranked = rank_results(rows)
        assert ranked[0]["id"] == 2  # higher similarity wins

    def test_score_in_range(self):
        rows = [
            {"id": 1, "similarity": 0.8, "_date_value": datetime.now().isoformat()},
        ]
        ranked = rank_results(rows)
        assert 0 <= ranked[0]["score"] <= 1.0

    def test_sorted_descending(self):
        rows = [
            {"id": 1, "similarity": 0.2, "_date_value": None},
            {"id": 2, "similarity": 0.9, "_date_value": None},
            {"id": 3, "similarity": 0.5, "_date_value": None},
        ]
        ranked = rank_results(rows)
        scores = [r["score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)


class TestEmbeddingDim:
    """Verify dimension constant matches Vector(384)."""

    def test_dim_is_384(self):
        assert EMBEDDING_DIM == 384
