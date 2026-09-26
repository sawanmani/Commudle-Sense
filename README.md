# Commudle Safe Natural-Language Search (PS-01)

> **Safe, permission-aware natural-language search** over Commudle's developer-community data.
> Supports **English, Hindi, and Hinglish** queries with structural injection defenses.

---

## Quick Start

```bash
# 1. Clone & setup
cp .env.example .env           # Add your GROQ_API_KEY
docker compose up -d db         # Or local PostgreSQL 16 + pgvector

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed the database (all 7 entities + embeddings)
python -m seed.seed_data

# 4. Run the API
uvicorn app.main:app --reload   # API on :8000

# 5. Run the demo UI
streamlit run demo/streamlit_app.py   # UI on :8501

# 6. Run tests
pytest tests/ -v

# 7. CLI demo
python scripts/demo_script.py
```

## Architecture

```
NL query
 -> [1] extraction.py    LLM fills SearchIntent (schema-locked)
 -> [2] validation.py    fuzzy-match to allow-lists; suspicious -> DROPPED
 -> [3] permissions.py   which columns may this role see
 -> [4] query_builder.py parameterized SELECT of ONLY allowed cols + cosine sim
 -> [5] ranking.py       score = 0.6*semantic + 0.4*recency
 -> results (+ optional DuckDuckGo enrichment, labeled external/unverified)
```

## Key Safety Features

- **LLM output is untrusted** — schema-locked to `SearchIntent` with `extra="forbid"`
- **No raw SQL** — SQLAlchemy Core with bound parameters only
- **Permission-checked** — visibility tags on every column; only `PUBLIC` projected
- **~48 regex patterns** for SQLi, prompt injection, role escalation, data exfiltration, XSS
- **Fuzzy allow-lists** — unknown values are dropped, never widened
- **Fail-closed** — any error returns `unknown` / `[]`, never widens access

## Tech Stack

| Layer | Choice |
|---|---|
| API | FastAPI + uvicorn |
| DB | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.0 (Core) |
| LLM | Groq (instructor structured output) |
| Embeddings | paraphrase-multilingual-MiniLM-L12-v2 (384-dim) |
| Validation | Pydantic + rapidfuzz |
| Web search | DuckDuckGo (keyless) |
| Demo UI | Streamlit |

## Test Coverage

- **20 normal queries** — all 7 entities, Hinglish, Devanagari, content_type, role
- **31 adversarial queries** — SQLi, prompt injection, role escalation, data exfiltration, XSS
- **Deterministic permission test** — proves no private column leaks for any entity × role

## Project Structure

```
app/
  config.py           # env + allow-list vocab
  schemas.py          # Pydantic models (SearchIntent)
  extraction.py       # Stage 1: NL -> SearchIntent
  validation.py       # Stage 2: allow-list + injection stripping
  permissions.py      # Stage 3: visible columns  [SACRED]
  query_builder.py    # Stage 4: parameterized query + cosine sim
  ranking.py          # Stage 5: hybrid scoring
  autocomplete.py     # bonus: safe pool suggestions
  external_search.py  # bonus: DuckDuckGo enrichment
  logging_utils.py    # bonus: audit log
  models.py           # SQLAlchemy tables  [SACRED]
  main.py             # FastAPI endpoints
seed/
  seed_data.py        # synthetic data generator
demo/
  streamlit_app.py    # Streamlit UI
scripts/
  demo_script.py      # CLI demo
tests/
  test_search.py, test_permissions.py
  data/normal_queries.json, adversarial_queries.json
```

## License

This project uses only synthetic/fake data. No real personal data is included.
