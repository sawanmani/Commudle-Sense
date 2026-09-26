"""
tests/test_search.py — Search pipeline tests.

- Normal queries: assert correct entity_type extraction + validation.
- Adversarial queries: assert pattern-flagged or dropped or entity==unknown.
"""

import json
import os

import pytest

from app.extraction import extract_intent
from app.validation import validate_intent, _SUSPICIOUS_RE

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_json(filename):
    with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)


# ── Normal queries ─────────────────────────────────────────────────────────────

class TestNormalQueries:
    """Test that normal queries extract the correct entity type."""

    @pytest.fixture(scope="class")
    def normal_cases(self):
        return _load_json("normal_queries.json")

    def test_normal_count(self, normal_cases):
        """Must have >= 20 normal test cases."""
        assert len(normal_cases) >= 20

    @pytest.mark.parametrize(
        "idx",
        range(20),
        ids=[f"normal_{i}" for i in range(20)],
    )
    def test_normal_query(self, normal_cases, idx):
        if idx >= len(normal_cases):
            pytest.skip("Not enough test cases")
        case = normal_cases[idx]
        intent = extract_intent(case["query"])
        clean, dropped = validate_intent(intent)
        assert clean.entity_type.value == case["expect_entity"], (
            f"Query: {case['query']!r} → got {clean.entity_type.value}, "
            f"expected {case['expect_entity']}"
        )


# ── Adversarial queries ────────────────────────────────────────────────────────

class TestAdversarialQueries:
    """Test that adversarial queries are blocked or neutralized."""

    @pytest.fixture(scope="class")
    def adversarial_cases(self):
        return _load_json("adversarial_queries.json")

    def test_adversarial_count(self, adversarial_cases):
        """Must have >= 15 adversarial test cases (we have 31)."""
        assert len(adversarial_cases) >= 15

    @pytest.mark.parametrize(
        "idx",
        range(31),
        ids=[f"adversarial_{i}" for i in range(31)],
    )
    def test_adversarial_query(self, adversarial_cases, idx):
        if idx >= len(adversarial_cases):
            pytest.skip("Not enough test cases")
        case = adversarial_cases[idx]
        query = case["query"]

        pattern_flagged = bool(_SUSPICIOUS_RE.search(query))

        intent = extract_intent(query)
        clean, dropped = validate_intent(intent)

        if case["expect_blocked"]:
            assert pattern_flagged or dropped or clean.entity_type.value == "unknown", (
                f"Adversarial query should be blocked: {query!r} "
                f"(category={case['category']})"
            )
        else:
            # XSS that should be stripped but still resolve
            assert clean.entity_type.value != "unknown", (
                f"Non-blocked adversarial should still resolve: {query!r}"
            )
