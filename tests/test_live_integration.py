"""Live-LLM smoke tests. Excluded by default; run occasionally with: pytest -m integration"""

import os

import pytest

from app.extraction import extract_intent
from app.validation import validate_intent

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="GROQ_API_KEY not set")]

CASES = [("Flutter developers in Lucknow", "speaker"), ("remote devops jobs", "job"),
         ("दिल्ली में मशीन लर्निंग पर workshop", "event"), ("blockchain communities", "community")]


@pytest.mark.parametrize("query,entity", CASES)
def test_live_extraction(query, entity):
    clean, _ = validate_intent(extract_intent(query))
    assert clean.entity_type.value == entity
