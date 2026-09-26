"""tests/test_backend.py — operational hardening + "spoken in" parsing (offline)."""

from datetime import date

import pytest
from sqlalchemy.exc import OperationalError

import app.main as main
from app.fallback_extraction import rule_based_intent
from app.ranking import rank_results
from app.schemas import SearchIntent
from app.validation import validate_intent

TODAY = date(2026, 9, 26)


# ── "spoken in" ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q,tech,spoken,home", [
    ("speakers on Flutter who have spoken in Lucknow", "flutter", "lucknow", None),
    ("Android speakers who spoke in Pune", "android", "pune", None),
    ("rust speakers who gave talks in Mumbai", "rust", "mumbai", None),
    ("Lucknow mein bol chuke Flutter speakers", "flutter", "lucknow", None),
    ("Python speakers in Delhi", "python", None, "delhi"),
])
def test_spoken_in_vs_home_city(q, tech, spoken, home):
    i = rule_based_intent(q, TODAY)
    assert i.entity_type.value == "speaker" and i.technologies == [tech]
    assert i.spoken_in == spoken and i.location == home


def test_spoken_in_is_validated_against_city_allow_list():
    clean, dropped = validate_intent(SearchIntent(entity_type="speaker", spoken_in="atlantis"))
    assert clean.spoken_in is None and any(d.startswith("spoken_in") for d in dropped)
    clean, _ = validate_intent(SearchIntent(entity_type="speaker", spoken_in="Lucknow"))
    assert clean.spoken_in == "lucknow"


def test_spoken_in_reaches_query_builder(client, calls):
    client.post("/search", json={"query": "speakers on Flutter who have spoken in Lucknow"})
    assert calls[0].spoken_in == "lucknow" and calls[0].location is None


# ── ranking: activity ─────────────────────────────────────────────────────────
def test_activity_lifts_busier_speakers():
    rows = [{"id": 1, "similarity": None, "_date_value": None, "_activity": 2},
            {"id": 2, "similarity": None, "_date_value": None, "_activity": 50}]
    ranked = rank_results(rows, None, w_sem=0.5, w_recency=0.3, w_activity=0.2)
    assert [r["id"] for r in ranked] == [2, 1]


def test_default_ranking_unchanged_without_activity_weight():
    rows = [{"id": 1, "similarity": 0.5, "_date_value": None, "_activity": 99}]
    assert rank_results(rows)[0]["score"] == rank_results([{**rows[0], "_activity": 0}])[0]["score"]


# ── API hardening ─────────────────────────────────────────────────────────────
def test_response_headers(client):
    r = client.post("/search", json={"query": "flutter events"})
    assert len(r.headers["x-request-id"]) == 12 and float(r.headers["x-process-time-ms"]) >= 0
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"


def test_client_cannot_choose_request_id(client):
    r = client.post("/search", json={"query": "flutter events"}, headers={"X-Request-ID": "evil\r\ninjected"})
    assert r.headers["x-request-id"] != "evil\r\ninjected"


def test_limit_is_validated_and_forwarded(client, monkeypatch):
    seen = {}
    real = main.build_and_run

    def spy(db, intent, ctx, emb=None, trace=None, limit=50):
        seen["limit"] = limit
        return real(db, intent, ctx, emb, trace, limit)

    monkeypatch.setattr(main, "build_and_run", spy)
    client.post("/search", json={"query": "flutter events", "limit": 5})
    assert seen["limit"] == 5
    assert client.post("/search", json={"query": "flutter events", "limit": 500}).status_code == 422
    assert client.post("/search", json={"query": "flutter events", "limit": 0}).status_code == 422


def test_database_outage_returns_clean_503_without_leaking_details(client, monkeypatch):
    def boom(*a, **k):
        raise OperationalError("SELECT secret_table FROM x", {}, Exception("password authentication failed for user postgres"))

    monkeypatch.setattr(main, "build_and_run", boom)
    r = client.post("/search", json={"query": "flutter events"})
    assert r.status_code == 503 and r.headers["retry-after"]
    body = r.text.lower()
    assert "secret_table" not in body and "password" not in body and r.json()["request_id"]


def test_vocabulary_endpoint(client):
    j = client.get("/vocabulary").json()
    assert "flutter" in j["technologies"] and "lucknow" in j["cities"] and "speaker" in j["entity_types"]


def test_ready_reports_503_when_db_down(client):
    class Dead:
        def execute(self, *a, **k):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def dead_db():
        yield Dead()

    main.app.dependency_overrides[main.get_db] = dead_db
    assert client.get("/ready").status_code == 503


def test_ready_ok_when_db_answers(client):
    class Alive:
        def execute(self, *a, **k):
            return 1

    def alive_db():
        yield Alive()

    main.app.dependency_overrides[main.get_db] = alive_db
    assert client.get("/ready").json() == {"ready": True, "database": "ok"}
