"""
tests/test_db_integration.py — the REAL pipeline against a REAL Postgres+pgvector, checked against
ground truth computed independently from seed/dummy_dataset.json.

Skipped automatically when no database is reachable (local runs without Docker). CI provides one.
The LLM is off (rule-based extraction), so these need no API key.
"""

import itertools
import json
import os
import sys

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "..", "seed", "dummy_dataset.json"), encoding="utf-8"))
KEY = {"community": "communities", "event": "events", "speaker": "speakers", "hackathon": "hackathons",
       "build": "builds", "lab": "labs", "job": "jobs"}
HAS_CITY = {"community", "event", "speaker", "hackathon", "lab", "job"}
EQUIV = {"fullstack": {"fullstack", "full stack"}, "full stack": {"fullstack", "full stack"}}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import app.main as main
    from app.models import engine
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no database reachable: {type(e).__name__}")
    from seed import load_dummy_dataset
    old = sys.argv
    sys.argv = ["load", "--if-empty"]
    try:
        load_dummy_dataset.main()
    finally:
        sys.argv = old
    main.search_limiter.calls = 10**9
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def quiet_log(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "log_blocked_attempt", lambda **kw: None)


def _search(client, monkeypatch, **intent_kw):
    """Run /search with a fixed intent (bypassing NL extraction) so the DB layer is what's under test."""
    import app.main as main
    from app.schemas import SearchIntent
    monkeypatch.setattr(main, "extract_with_source", lambda q: (SearchIntent(**intent_kw), "test"))
    return client.post("/search", json={"query": "x y z", "limit": 50}).json()


def _exact_ids(j):
    """Ids of exact matches only (broadened fallback results are labelled and excluded)."""
    return {r["id"] for r in j["results"] if not any(m.startswith("broader match") for m in r["match_reasons"])}


def _tags(row):
    return {t.strip() for t in row["tags"].split(",")}


def _expected(ent, tech=None, city=None):
    out = set()
    for row in DATA[KEY[ent]]:
        if tech and not (EQUIV.get(tech, {tech}) & _tags(row)):
            continue
        if city and ent in HAS_CITY and row["city"] != city:
            continue
        out.add(row["id"])
    return out


@pytest.mark.parametrize("ent", list(KEY))
def test_tech_and_city_filters_match_ground_truth(client, monkeypatch, ent):
    checked = 0
    for tech, city in itertools.product(["go", "react", "java", "ios", "ml", "python", "fullstack", "web3"], [None, "lucknow", "remote"]):
        exp = _expected(ent, tech, city)
        if len(exp) > 50:
            continue
        got = _exact_ids(_search(client, monkeypatch, entity_type=ent, technologies=[tech], location=city))
        assert got == exp, f"{ent}/{tech}/{city}: extra={sorted(got - exp)[:5]} missing={sorted(exp - got)[:5]}"
        checked += 1
    assert checked >= 15


def test_go_does_not_return_django_rows(client, monkeypatch):
    rows = {r["id"]: r for r in DATA["speakers"]}
    for hit in _search(client, monkeypatch, entity_type="speaker", technologies=["go"])["results"]:
        assert "go" in _tags(rows[hit["id"]])


@pytest.mark.parametrize("ent,col", [("event", "event_date"), ("hackathon", "start_date")])
@pytest.mark.parametrize("lo,hi", [("2026-10-01", "2026-10-31"), ("2026-09-26", "2026-12-31"), ("2027-01-01", "2027-03-31")])
def test_date_ranges_match_ground_truth(client, monkeypatch, ent, col, lo, hi):
    exp = {r["id"] for r in DATA[KEY[ent]] if lo <= r[col] <= hi}
    got = _exact_ids(_search(client, monkeypatch, entity_type=ent, date_range={"from_date": lo, "to_date": hi}))
    assert got == exp


@pytest.mark.parametrize("city", ["lucknow", "delhi", "pune", "mumbai", "remote", "jaipur"])
def test_spoken_in_matches_ground_truth(client, monkeypatch, city):
    events = {e["id"]: e for e in DATA["events"]}
    exp = {t["speaker_id"] for t in DATA["speaker_talks"] if events[t["event_id"]]["city"] == city}
    got = _exact_ids(_search(client, monkeypatch, entity_type="speaker", spoken_in=city))
    assert got == exp and exp, "dataset should have speakers who spoke in this city"


def test_spoken_in_combines_with_technology(client, monkeypatch):
    events = {e["id"]: e for e in DATA["events"]}
    speakers = {s["id"]: s for s in DATA["speakers"]}
    exp = {t["speaker_id"] for t in DATA["speaker_talks"]
           if events[t["event_id"]]["city"] == "delhi" and "python" in _tags(speakers[t["speaker_id"]])}
    got = _exact_ids(_search(client, monkeypatch, entity_type="speaker", technologies=["python"], spoken_in="delhi"))
    assert got == exp


def test_natural_language_speakers_who_spoke_in_city(client):
    j = client.post("/search", json={"query": "speakers on Flutter who have spoken in Lucknow"}).json()
    assert j["interpreted_intent"]["spoken_in"] == "lucknow" and j["interpreted_intent"]["location"] is None
    events = {e["id"]: e for e in DATA["events"]}
    who = {t["speaker_id"] for t in DATA["speaker_talks"] if events[t["event_id"]]["city"] == "lucknow"}
    assert _exact_ids(j) <= who


def test_limit_is_respected(client, monkeypatch):
    import app.main as main
    from app.schemas import SearchIntent
    monkeypatch.setattr(main, "extract_with_source", lambda q: (SearchIntent(entity_type="event"), "test"))
    assert len(client.post("/search", json={"query": "events", "limit": 7}).json()["results"]) == 7


@pytest.mark.parametrize("role", ["logged_out", "member", "organiser"])
@pytest.mark.parametrize("ent", list(KEY))
def test_no_private_value_ever_leaves_the_api(client, monkeypatch, role, ent):
    import app.main as main
    from app.schemas import SearchIntent
    monkeypatch.setattr(main, "extract_with_source", lambda q: (SearchIntent(entity_type=ent), "test"))
    body = client.post("/search", json={"query": "x y z", "context": {"auth_state": role}, "limit": 50}).text
    private = ["@example.invalid", "+91-000", "RSVP-", "ATT-", "REG-", "APP-", "chan-", "T-shirt", "conflict of interest",
              "DRAFT v", "Budget shortfall", "page_views", "conversion_pct"]
    assert not [m for m in private if m in body]


def test_generated_sql_only_selects_public_columns(client, monkeypatch):
    import app.config as config
    monkeypatch.setattr(config, "ENABLE_TRACE", True)
    import app.main as main
    from app.schemas import SearchIntent
    for ent in KEY:
        monkeypatch.setattr(main, "extract_with_source", lambda q, e=ent: (SearchIntent(entity_type=e), "test"))
        j = client.post("/search", json={"query": "x y z", "debug": True}).json()
        step = next(s for s in j["trace"] if s["stage"].startswith("6"))
        select_part = step["sql"].split("FROM")[0].lower()
        for hidden in step["hidden_columns"]:
            assert hidden["column"] not in select_part, f"{ent}: {hidden['column']} selected!"
        assert "embedding" not in select_part or ent in ("event", "speaker")


def test_stored_injection_rows_are_redacted_from_real_db(client, monkeypatch):
    poisoned = {r["id"] for k in ("speakers",) for r in DATA[k] if "Ignore all previous" in r["bio"] or "<script>" in r["bio"]}
    if not poisoned:
        pytest.skip("no poisoned speaker rows in this dataset")
    from app.config import KNOWN_CITIES
    seen = []
    for city in KNOWN_CITIES:  # results are capped at 50, so sweep by city to reach every row
        seen += _search(client, monkeypatch, entity_type="speaker", location=city)["results"]
    for r in seen:
        assert "ignore all previous" not in r["snippet"].lower() and "<script" not in r["snippet"].lower()
    assert any(r["id"] in poisoned and r["snippet"].startswith("[content removed") for r in seen)


def test_ready_endpoint_with_real_db(client):
    assert client.get("/ready").json() == {"ready": True, "database": "ok"}


def test_sql_injection_string_as_a_value_is_just_data(client, monkeypatch):
    """Even if a hostile value reached the builder it is a bound parameter, and tables survive."""
    import app.main as main
    from app.schemas import SearchIntent
    evil = "x'; DROP TABLE speakers; --"
    monkeypatch.setattr(main, "extract_with_source", lambda q: (SearchIntent(entity_type="speaker", location=evil), "test"))
    assert client.post("/search", json={"query": "x y z"}).status_code == 200  # validated away, not executed
    assert _search(client, monkeypatch, entity_type="speaker")["results"], "speakers table must still exist"


# ── ordering, metadata, semantic ─────────────────────────────────────────────
@pytest.mark.parametrize("ent,key,col", [("hackathon", "hackathons", "start_date"), ("event", "events", "event_date")])
def test_time_bound_results_are_upcoming_first_soonest_first(client, monkeypatch, ent, key, col):
    from datetime import date
    today = date.today().isoformat()
    j = _search(client, monkeypatch, entity_type=ent, location="delhi")
    dates = [r["date"] for r in j["results"]]
    exp = sorted([r[col] for r in DATA[key] if r["city"] == "delhi"], key=lambda d: (d < today, d if d >= today else ""))
    upcoming = [d for d in dates if d >= today]
    past = [d for d in dates if d < today]
    assert dates == upcoming + past, "every upcoming item must come before every past one"
    assert upcoming == sorted(upcoming) and past == sorted(past, reverse=True)
    assert len(dates) == len(exp)
    assert all(r["status"] in ("upcoming", "today", "past") for r in j["results"])


def test_result_items_carry_public_metadata_and_reasons(client, monkeypatch):
    tech, city = next((t, h["city"]) for h in DATA["hackathons"] for t in sorted(_tags(h)) if h["city"] != "remote")
    j = _search(client, monkeypatch, entity_type="hackathon", technologies=[tech], location=city)
    assert j["results"]
    for r in j["results"]:
        assert r["city"] == city and tech in r["tags"] and r["date"]
        assert f"tech: {tech}" in r["match_reasons"] and f"in {city.title()}" in r["match_reasons"]


def test_scores_use_full_range_without_semantic_vectors(client, monkeypatch):
    j = _search(client, monkeypatch, entity_type="hackathon", location="pune")
    upcoming = [r for r in j["results"] if r["status"] != "past"]
    if upcoming:
        assert upcoming[0]["score"] > 0.5, "no longer capped at 0.4 when semantic search is off"


@pytest.mark.semantic
def test_semantic_search_ranks_by_meaning(client, monkeypatch):
    pytest.importorskip("sentence_transformers")
    import app.config as config
    from app import ranking
    monkeypatch.setattr(config, "ENABLE_EMBEDDINGS", True)
    ranking.get_embedder(block=True)  # tests may wait for the model; users never do
    import app.main as main
    from app.schemas import SearchIntent
    monkeypatch.setattr(main, "extract_with_source", lambda q: (SearchIntent(
        entity_type="event", free_text_remainder="machine learning and AI workshop"), "test"))
    j = client.post("/search", json={"query": "machine learning and AI workshop", "limit": 10}).json()
    assert j["results"] and all(any(m.startswith("meaning match") for m in r["match_reasons"]) for r in j["results"])
    events = {e["id"]: e for e in DATA["events"]}
    top = [events[r["id"]] for r in j["results"][:5]]
    assert sum(1 for e in top if {"ml", "genai"} & _tags(e)) >= 3, [e["title"] for e in top]


def test_no_exact_match_broadens_and_labels_results(client, monkeypatch):
    # dataset has React events, but none in Delhi
    assert not _expected("event", "react", "delhi") and _expected("event", "react")
    j = _search(client, monkeypatch, entity_type="event", technologies=["react"], location="delhi")
    assert j["results"], "should fall back to React events in other cities"
    assert any("No exact matches" in n for n in j["notes"])
    for r in j["results"]:
        assert "react" in r["tags"] and any(m.startswith("broader match") for m in r["match_reasons"])


def test_exact_matches_are_never_labelled_broader(client, monkeypatch):
    j = _search(client, monkeypatch, entity_type="hackathon", location="delhi")
    assert j["results"] and not any("broader" in m for r in j["results"] for m in r["match_reasons"])
