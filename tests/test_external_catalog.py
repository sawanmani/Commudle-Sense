"""tests/test_external_catalog.py — external (other platforms) catalog: coverage, safety, ranking."""

import json

import pytest

from app import external_catalog as ec
from app.schemas import SearchIntent, EntityType, DateRange

ROWS = json.load(open(ec.DATASET_PATH, encoding="utf-8"))


def _intent(entity, techs=(), city=None, **kw):
    return SearchIntent(entity_type=EntityType(entity), technologies=list(techs), location=city, **kw)


def test_dataset_has_700_entries_with_links_on_every_row():
    assert len(ROWS) == 700
    assert all(r["redirect_url"] and r["is_synthetic"] for r in ROWS)
    assert len({r["source_platform"] for r in ROWS}) == 8


def test_every_redirect_url_is_https_and_allowlisted():
    assert all(ec._safe_url(r["redirect_url"]) for r in ROWS)


@pytest.mark.parametrize("bad", ["http://devfolio.co/x", "https://evil.example/x", "javascript:alert(1)", "", None])
def test_unsafe_urls_rejected(bad):
    assert ec._safe_url(bad) is None


def test_exact_match_ranks_first_and_respects_filters():
    hits = ec.search_external(_intent("hackathon", ["flutter"], "lucknow"))
    assert hits and hits[0]["match_level"] == "exact"
    exact = [h for h in hits if h["match_level"] in ("exact", "online")]
    by_id = {r["id"]: r for r in ROWS}
    assert all("flutter" in by_id[h["id"]]["technologies"] for h in exact)
    assert all(by_id[h["id"]]["city"] in ("lucknow", "remote") for h in exact)
    assert all(h["match_level"] == "online" for h in exact if by_id[h["id"]]["city"] == "remote")


@pytest.mark.parametrize("entity", ["community", "event", "speaker", "hackathon", "build", "lab", "job"])
def test_every_entity_type_returns_something(entity):
    assert ec.search_external(_intent(entity, ["python"], "delhi"))


def test_unknown_entity_returns_nothing():
    assert ec.search_external(_intent("unknown", ["python"])) == []


def test_stored_injection_is_redacted():
    inj = [r for r in ROWS if ec._SUSPICIOUS_RE.search(r["description"])]
    assert inj, "dataset should contain poisoned descriptions"
    for r in inj[:5]:
        assert ec._safe_text(r["description"], 300) == ec.REDACTED
    for e in {r["entity_type"] for r in inj}:
        for h in ec.search_external(_intent(e), limit=50):
            assert not ec._SUSPICIOUS_RE.search(h["snippet"])


def test_date_range_filters():
    hits = ec.search_external(_intent("hackathon", date_range=DateRange(from_date="2027-01-01", to_date="2027-12-31")), limit=50)
    by_id = {r["id"]: r for r in ROWS}
    assert all(by_id[h["id"]]["start_date"] >= "2027-01-01" for h in hits)


def test_missing_dataset_fails_closed(monkeypatch):
    monkeypatch.setattr(ec, "_catalog", None)
    monkeypatch.setattr(ec, "DATASET_PATH", "does/not/exist.json")
    assert ec.search_external(_intent("hackathon", ["python"])) == []
    monkeypatch.setattr(ec, "_catalog", None)
