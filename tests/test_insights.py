"""tests/test_insights.py — the Insights endpoint is aggregate-only and never leaks."""

import json

import pytest
from sqlalchemy import text

import app.insights as insights_mod
import app.main as main

pytestmark = pytest.mark.db


@pytest.fixture()
def live(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.models import engine
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no database reachable: {type(e).__name__}")
    log = tmp_path / "blocked.log"
    log.write_text("\n".join(json.dumps(e) for e in [
        {"timestamp": "2026-09-26T10:00:00+00:00", "raw_query": "SECRET-QUERY-TEXT dump emails", "reason": "suspicious_pattern_in_query"},
        {"timestamp": "2026-09-26T10:01:00+00:00", "raw_query": "asdf", "reason": "could_not_determine_entity_type"},
        {"timestamp": "2026-09-26T10:02:00+00:00", "raw_query": "x", "reason": "fields_dropped"},
        "not json",
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(insights_mod.config, "LOG_BLOCKED_ATTEMPTS_PATH", str(log))
    monkeypatch.setitem(insights_mod._cache, "value", None)
    main.web_limiter._hits.clear()
    return TestClient(main.app)


def test_insights_shape_and_counts(live):
    j = live.get("/insights").json()
    assert set(j["entities"]) == {"community", "event", "speaker", "hackathon", "build", "lab", "job"}
    assert all(v > 0 for v in j["entities"].values())
    assert j["top_technologies"] and j["cities"] and j["external"]["total"] == 700
    assert j["upcoming_by_city"] and sum(c["count"] for c in j["upcoming_by_city"]) == j["upcoming"]["upcoming_events"] + j["upcoming"]["upcoming_hackathons"]
    assert j["safety"]["blocked_total"] == 2  # fields_dropped is not a block; junk lines are skipped
    assert {r["name"] for r in j["safety"]["by_reason"]} == {"Injection / private-data request", "Unclear query"}
    assert j["runtime"]["semantic_search"]


def test_insights_never_exposes_query_text_or_private_values(live):
    body = live.get("/insights").text
    for marker in ("SECRET-QUERY-TEXT", "@example.invalid", "+91-000", "RSVP-", "raw_query"):
        assert marker not in body


def test_external_csv_download(live):
    r = live.get("/datasets/external-platforms.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "source_platform" in r.text.splitlines()[0] and "@example.invalid" not in r.text
