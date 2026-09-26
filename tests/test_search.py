"""
tests/test_search.py — Deterministic (offline) search pipeline tests.

- Normal queries: rule-based extraction + validation must give the expected entity.
- Adversarial queries: the API must block every one BEFORE anything reaches the query builder.
Live-LLM equivalents live in tests/test_live_integration.py (marked integration).
"""

import json
import os

import pytest

from app.extraction import extract_intent
from app.validation import validate_intent

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


NORMAL = _load("normal_queries.json")
ADVERSARIAL = _load("adversarial_queries.json")


def test_dataset_sizes():
    assert len(NORMAL) >= 20 and len(ADVERSARIAL) >= 15


@pytest.mark.parametrize("case", NORMAL, ids=[c["query"][:40] for c in NORMAL])
def test_normal_query_extracts_expected_entity(case):
    clean, _ = validate_intent(extract_intent(case["query"]))
    assert clean.entity_type.value == case["expect_entity"]


@pytest.mark.parametrize("case", NORMAL, ids=[c["query"][:40] for c in NORMAL])
def test_normal_query_through_api_is_not_blocked(client, calls, case):
    body = {"query": case["query"], "context": {"auth_state": case["auth_state"]}}
    r = client.post("/search", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["blocked"] is False
    assert j["interpreted_intent"]["entity_type"] == case["expect_entity"]
    assert len(calls) == 1


@pytest.mark.parametrize("case", ADVERSARIAL, ids=[c["category"] + ":" + c["query"][:30] for c in ADVERSARIAL])
def test_adversarial_query_blocked_before_query_builder(client, calls, case):
    r = client.post("/search", json={"query": case["query"], "context": {"auth_state": case["auth_state"]}})
    assert r.status_code == 200
    j = r.json()
    assert j["blocked"] is True and j["results"] == [] and j["external_results"] == []
    assert calls == [], "a blocked query must never reach the database layer"
