# Commudle Safe Search

[![CI](https://github.com/sawanmani/Commudle-Sense/actions/workflows/ci.yml/badge.svg)](https://github.com/sawanmani/Commudle-Sense/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11-blue) ![license](https://img.shields.io/badge/license-MIT-green)

**Ask in plain English, Hindi or Hinglish. Get ranked results from Commudle _and_ other platforms — without ever exposing private data.**

> "Flutter developers near me" · "Lucknow ke aas paas Android developers" · "दिल्ली में मशीन लर्निंग पर workshop" · "web3 hackathons next month"

Built for **PS-01: Safe Natural-Language Search for Commudle**. The language model is an *untrusted* JSON extractor. It never sees the database, and every safety rule is enforced in code, not in a prompt.

---

## Launch in one command

```bash
python scripts/launch.py        # Postgres+pgvector (Docker) → seed → API :8000 → UI :8501 → opens browser
```

or fully containerised:

```bash
docker compose up --build       # UI http://localhost:8501 · API docs http://localhost:8000/docs
```

No API key needed. Without `GROQ_API_KEY` (or when Groq is rate-limited) a deterministic rule-based extractor takes over.
Add a key to `.env` for LLM extraction. Requires Python 3.11 and Docker.

## What you get

| | |
|---|---|
| **Two result sections** | 📍 **Local** (Commudle database) and 🌐 **Other platforms** (Devfolio, Devpost, Unstop, HackerEarth, Hack2Skill, DoraHacks, Commudle, Luma), each hit with an *Open on platform ↗* link |
| **Natural language → query** | technology · city · date range (`upcoming`, `next month`, `in October`) · role · content type · sort |
| **"Spoke in"** | "speakers on Flutter who have **spoken in** Lucknow" is a different question from "speakers **in** Lucknow" — it filters on the events a speaker actually talked at |
| **"Near me"** | resolved from the requester's city; asks *"Which city?"* if unknown |
| **Clarifying questions** | ambiguous query → asks what you're looking for instead of guessing |
| **Hinglish + Hindi** | LLM path and rule-based path both understand Devanagari and Latin-script Hindi |
| **Semantic (hybrid) search** | a local multilingual model (`paraphrase-multilingual-MiniLM-L12-v2`) turns the query into a meaning vector; pgvector orders by closeness, combined with the structured filters. Loads in the background at start-up; searches never wait for it |
| **Ranking** | events and hackathons: **upcoming first, soonest first, past below**; plus meaning similarity and activity (talks given / community size). Signals a result type doesn't have are dropped and the rest re-weighted, so scores use the full 0–1 range |
| **Never an empty page** | no exact match → the search is re-run with one filter removed ("React events in other cities") and those results are labelled *broader match* |
| **Why it matched** | each local result carries its date, upcoming/past status, city, tags and the reasons it matched |
| **Audit log** | every blocked/dropped attempt is written to `logs/blocked_attempts.log` |

## How it stays safe

```
query ─▶ 0 guard ─▶ 1 extract ─▶ 2 validate ─▶ 3 permissions ─▶ 4 parameterised SQL ─▶ 5 rank ─▶ redact ─▶ response
        (block)     (LLM|rules)   (allow-lists)  (public cols)    (bound params only)              (stored text)
```

| Threat | Defence (all in code) |
|---|---|
| Prompt injection in the query | **Guard** runs *before* any LLM call: Unicode-normalises (kills zero-width tricks), then regex-blocks injection, SQLi, role escalation, exfiltration, XSS — in English, Hindi and Hinglish. The whole request is refused. |
| Injection stored in the database | Titles/snippets of every result are scanned and **redacted** before leaving the API. The external catalog does the same and only emits allow-listed `https` links. |
| Model invents fields or values | `SearchIntent` is schema-locked (`extra="forbid"`); every value is fuzzy-matched to a closed vocabulary — unknown values are **dropped, never widened**. |
| Private-data leakage | Each column is tagged `public` / `private` / `organiser_only`; the query builder selects **only** `public` columns for every role. Emails, phones, RSVPs, attendance, form responses, private channels, drafts and organiser analytics are structurally unselectable. |
| SQL injection | SQLAlchemy Core with bound parameters; SQL is never built from strings. |
| Model with raw DB access | The model only ever outputs a validated `SearchIntent`. It has no connection, no tools. |
| Quota drain / scripted abuse | Per-IP rate limits (in-memory, per API worker — use Redis for a strict global limit) on `/search` (30/min) and `/web-enrich` (10/min); the LLM has a **circuit breaker** — a 429 pauses LLM calls for 60 s and the rule-based path serves meanwhile. |
| Query in URLs / logs | `POST /search` takes a JSON **body**; nothing searchable is placed in the URL. |
| Cross-origin abuse | CORS allows only configured origins (`CORS_ORIGINS`), no wildcard, no credentials. |

> **Note on `role`.** `role` (speaker / mentor / organiser …) is extracted and shown in the interpreted intent but is intentionally **not** a database filter: no searchable table has a public role column, and adding one would widen what search can see. It is a classification signal, not a missing feature.
> Likewise, entities with no `city` column (e.g. builds) ignore the location filter and say so in the response `notes`.

## API

```bash
curl -X POST localhost:8000/search -H 'Content-Type: application/json' -d '{
  "query": "Flutter hackathons in Lucknow",
  "context": {"auth_state": "member", "city": "lucknow"}
}'
```

`auth_state` is `logged_out | member | organiser`. Response (abridged):

```jsonc
{
  "results":          [ { "entity_type": "hackathon", "id": 7, "title": "…", "snippet": "…", "score": 0.91 } ],   // local
  "external_results": [ { "source_platform": "Devfolio", "title": "…", "redirect_url": "https://devfolio.co/hackathons",
                          "match_level": "exact", "is_synthetic": true } ],                                        // other platforms
  "blocked": false, "clarifying_question": null, "notes": [], "interpreted_intent": { … }
}
```

`limit` (1–50, default 20) caps local results; `debug: true` returns a step-by-step trace with the generated SQL when the server runs with `ENABLE_TRACE=true` (demo only — it reveals schema details).

Also: `GET /autocomplete?q=` · `GET /web-enrich?q=` (guarded, rate-limited) · `GET /vocabulary` (allowed technologies / cities / …) · `GET /health` (process up) · `GET /ready` (database answers; `503` otherwise).

Every response carries a server-generated `X-Request-ID`, `X-Process-Time-ms` and safe headers (`nosniff`, `no-store`). A database outage returns a clean `503` + `Retry-After` with no driver or SQL details.

## Data

Everything is **synthetic** — no real personal data anywhere.

| Dataset | Records | Purpose |
|---|---|---|
| [`seed/dummy_dataset.json`](seed/dummy_dataset.json) | 1,239 | Local Commudle DB: 7 searchable entities + users, **every column filled** (incl. fake private fields to prove they never leak), every city evenly covered (e.g. 6 hackathons and 15 events per city), 414 speaker→event links matched to speakers' skills ("spoke in" queries), ~6 % rows carrying stored injection payloads, ~14 % Hindi/Hinglish |
| [`seed/external_platforms_dataset.json`](seed/external_platforms_dataset.json) / [`.csv`](seed/external_platforms_dataset.csv) | 700 | "Other platforms": 8 platforms, 7 entity types, all 31 technologies × 15 cities, 33 columns |

External entries are invented; `redirect_url` opens the **platform's real public listing page** (never a fabricated deep link), so you can verify the platform and browse real entries. Regenerate with `python -m seed.generate_dummy_dataset` / `python -m seed.generate_external_dataset`.

## Develop & test

```bash
pip install -r requirements.txt
pytest                         # 280+ tests. No API key needed. The ~60 real-Postgres tests run when DATABASE_URL is reachable
                               # (python scripts/launch.py starts one) and skip themselves otherwise
pytest -m integration          # a few live-Groq smoke tests (needs GROQ_API_KEY) — run occasionally
ruff check .
python -m scripts.stress_test 150 4      # in-process stress with dataset-derived + adversarial queries
python scripts/http_load_test.py http://127.0.0.1:8000 3000 32   # concurrent load over real HTTP (start the server with RATE_LIMIT_SEARCH=100000/60)
```

The test suite covers 20 normal and 31 adversarial queries end-to-end through the API (every adversarial one must be blocked *before* the query builder is reached), permission checks per entity × role, the extraction fallback and circuit breaker, the rate limiter, CORS and redaction. CI (`.github/workflows/ci.yml`) runs lint + the full suite, including the database tests against a pgvector service container, on every push. The DB tests compare live search results with ground truth computed independently from the dataset (filters, date ranges, "spoke in", private-column leaks).

## Layout

```
app/    guard.py · models_extra.py · extraction.py · fallback_extraction.py · validation.py · permissions.py [protected]
        query_builder.py · ranking.py · external_catalog.py · ratelimit.py · models.py [protected] · main.py
seed/   generators + loaders for both datasets        demo/   Streamlit UI (client of the real API)
tests/  offline suite + live integration tests        scripts/ launch.py · stress_test.py · demo_script.py
```

Semantic search needs `sentence-transformers` + `torch` (in `requirements.txt`; the Docker image skips them unless built with `--build-arg EMBEDDINGS=true`). Without them everything still works with filters + ranking. Each API worker holds its own copy of the model (~1.2 GB RAM), so the launcher defaults to 2 workers (`WORKERS=` to change).

## License

MIT — see [LICENSE](LICENSE).
