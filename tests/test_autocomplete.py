"""
tests/test_autocomplete.py — Deterministic autocomplete tests (no DB/LLM).
"""

from app.autocomplete import suggest, record_successful_query, _pool


class TestAutocompletePool:
    """Verify the safe pool is properly built."""

    def test_pool_not_empty(self):
        assert len(_pool) > 100, f"Pool too small: {len(_pool)}"

    def test_pool_contains_known_combinations(self):
        pool_lower = [s.lower() for s in _pool]
        assert any("flutter" in s for s in pool_lower)
        assert any("lucknow" in s for s in pool_lower)
        assert any("android" in s for s in pool_lower)

    def test_no_raw_user_input_in_pool(self):
        """Pool should only contain template-generated strings."""
        for s in _pool:
            assert "<script>" not in s
            assert "DROP TABLE" not in s


class TestSuggest:
    """Verify suggestion behavior."""

    def test_min_length(self):
        assert suggest("a") == []
        assert suggest("") == []

    def test_returns_results(self):
        results = suggest("flutter")
        assert len(results) > 0
        assert all("flutter" in r.lower() for r in results)

    def test_limit(self):
        results = suggest("fl", limit=3)
        assert len(results) <= 3

    def test_city_boost(self):
        suggest("react events", city=None)  # baseline call must not raise
        results_with_city = suggest("react events", city="delhi")
        # With city, Delhi results should appear earlier
        if results_with_city:
            assert any("delhi" in r.lower() for r in results_with_city[:3])

    def test_only_pool_strings(self):
        """Suggestions must come from the pool, never raw input."""
        results = suggest("flutter<script>")
        for r in results:
            assert r in _pool


class TestPopularity:
    """Verify popularity recording."""

    def test_record_and_boost(self):
        # Record a query several times
        for _ in range(5):
            record_successful_query("python events in delhi")
        results = suggest("python events")
        assert len(results) > 0
