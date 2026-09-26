"""tests/test_extraction.py — LLM path mocked: fallback, circuit breaker, gap filling."""

from datetime import date

from app import config, extraction
from app.schemas import EntityType, SearchIntent

TODAY = date(2026, 9, 26)


def _enable_llm(monkeypatch):
    monkeypatch.setattr(config, "LLM_EXTRACTION_ENABLED", True)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")


def test_llm_result_is_used_when_confident(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(extraction, "_llm_intent", lambda q, t: SearchIntent(entity_type="speaker", technologies=["rust"]))
    out = extraction.extract_intent("speakers who know Rust", TODAY)
    assert out.entity_type == EntityType.speaker and out.technologies == ["rust"]


def test_llm_unknown_falls_back_to_rules(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(extraction, "_llm_intent", lambda q, t: SearchIntent(entity_type="unknown"))
    assert extraction.extract_intent("Android events in Bangalore", TODAY).entity_type == EntityType.event


def test_llm_gaps_filled_with_resolved_dates(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(extraction, "_llm_intent", lambda q, t: SearchIntent(entity_type="event", technologies=["flutter"]))
    out = extraction.extract_intent("Flutter events next month", TODAY)
    assert (out.date_range.from_date, out.date_range.to_date) == ("2026-10-01", "2026-10-31")


def test_rate_limit_trips_breaker_then_skips_llm(monkeypatch):
    _enable_llm(monkeypatch)
    attempts = []

    def boom():
        attempts.append(1)
        raise RuntimeError("Error code: 429 - rate_limit_exceeded")

    monkeypatch.setattr(extraction, "_build_client", boom)
    first = extraction.extract_intent("python labs in Mumbai", TODAY)
    assert first.entity_type == EntityType.lab and len(attempts) == 1
    assert extraction.llm_available() is False
    extraction.extract_intent("python labs in Pune", TODAY)
    assert len(attempts) == 1, "breaker open: the LLM must not be called again"


def test_any_exception_returns_fallback_not_raise(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(extraction, "_build_client", lambda: (_ for _ in ()).throw(ValueError("bad")))
    assert extraction.extract_intent("remote devops jobs", TODAY).entity_type == EntityType.job


def test_garbage_gives_unknown():
    assert extraction.extract_intent("asdf qwerty", TODAY).entity_type == EntityType.unknown
    assert extraction.extract_intent("", TODAY).entity_type == EntityType.unknown


def test_relative_dates():
    from app.fallback_extraction import rule_based_intent as r
    assert r("hackathons in October", TODAY).date_range.from_date == "2026-10-01"
    assert r("upcoming events", TODAY).date_range.from_date == "2026-09-26"
    assert r("events this month", TODAY).date_range.to_date == "2026-09-30"
    assert r("events next month", date(2026, 12, 5)).date_range.from_date == "2027-01-01"


def test_llm_answer_is_cached_and_copies_are_independent(monkeypatch):
    _enable_llm(monkeypatch)
    n = []

    def fake(q, t):
        n.append(q)
        return SearchIntent(entity_type="speaker", technologies=["rust"])

    monkeypatch.setattr(extraction, "_llm_intent", fake)
    a, src_a = extraction.extract_with_source("Rust  speakers", TODAY)
    a.technologies.append("mutated")
    b, src_b = extraction.extract_with_source("rust speakers", TODAY)
    assert len(n) == 1 and src_a == "llm" and src_b == "llm · cached"
    assert b.technologies == ["rust"], "cache must hand out copies"


def test_rule_answers_are_not_cached(monkeypatch):
    extraction.extract_with_source("python labs", TODAY)
    assert not extraction._cache


def test_breaker_honours_provider_retry_hint(monkeypatch):
    _enable_llm(monkeypatch)
    assert extraction._cooldown_for("Rate limit reached ... Please try again in 6m27.9s.") > 380
    assert extraction._cooldown_for("try again in 5h") == 3600
    assert extraction._cooldown_for("Connection error") == config.LLM_COOLDOWN_SECONDS
