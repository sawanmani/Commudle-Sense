# AGENTS.md — working on Commudle Search with an AI assistant

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot…) and for humans pairing with them.
Read this before changing anything. Companion docs: [`conflict.md`](conflict.md) (known clashes and fixes),
[`IMPROVEMENTS.md`](IMPROVEMENTS.md) (what to build next), [`docs/GUIDED_LEARNING.md`](docs/GUIDED_LEARNING.md)
(learn the codebase step by step), [`DEPLOY.md`](DEPLOY.md).

## What this is
PS-01 **safe natural-language search** for Commudle: people type "Android developers near me" or
"दिल्ली में मशीन लर्निंग पर workshop"; the system turns the sentence into validated filters, runs a
permission-checked query over **synthetic** data, ranks results, and blocks prompt injection and private-data
requests. Live: UI https://commudle-search.vercel.app · API https://commudle-search-api.onrender.com

## The pipeline (one request, in order) — know which file owns each stage
| # | Stage | File(s) | Contract |
|---|---|---|---|
| 1 | Input | `app/main.py` (`POST /search`) | query in the JSON body, requester `context` (role, city) |
| 2 | Safety guard | `app/guard.py` | runs **before** LLM/DB/web; blocks → `block_category` + message |
| 3 | Understand | `app/extraction.py` (LLM, Groq) · `app/fallback_extraction.py` (rules) | returns a `SearchIntent`; LLM is untrusted; rules take over on failure/429 |
| 4 | Validate | `app/validation.py` · `app/fuzzy.py` | every value mapped onto closed allow-lists in `app/config.py`; unknown → dropped |
| 5 | Choose & embed | `app/main.py` · `app/ranking.py` | one type, or all types if none named; meaning vector if model ready |
| 6 | Permission-checked SQL | `app/query_builder.py` · `app/permissions.py` · `app/audience.py` | PUBLIC columns only; row audience by role; bound parameters only |
| 7 | Rank | `app/ranking.py` · `app/main.py::_rank` | meaning + timeliness/recency + activity; broaden if empty |
| 8 | Clean stored text | `app/validation.py::redact_suspicious` | DB text is untrusted too |
| 9 | Other platforms | `app/external_catalog.py` | same validated filters over `seed/external_platforms_dataset.json` |

Frontend (`frontend/`, React + Vite): `App.jsx` (state, routing) · `SearchHero.jsx` (search box, examples,
attack demo) · `Results.jsx` · `DeepSearchLoader.jsx` (Lottie) · `pages/` (Insights, Workflow, Resources) ·
`api.js` (HTTP client, wake-up retries).

## Non-negotiable rules — never break these
1. **`app/models.py` and `app/permissions.py` are protected** (`[SACRED]`). Don't edit them. Need new data?
   Add a table to `app/models_extra.py` and apply it in `query_builder.py`.
2. **Only PUBLIC columns ever leave the database.** Emails, phones, RSVPs, attendance, form responses,
   private channels, drafts, organiser notes/analytics are unselectable for *every* role.
3. **No SQL from strings.** SQLAlchemy expressions with bound parameters only (no f-strings into SQL).
4. **The model never touches the database.** The LLM only fills `SearchIntent` (`extra="forbid"`).
5. **Guard first, fail closed.** Anything suspicious stops at stage 2; any error returns less, never more.
6. **Allow-lists live in `app/config.py`** and are never extended from user or LLM input.
7. **Stored and external text is untrusted** — redact before returning it.
8. **Synthetic data only.** Never add real people, emails or phone numbers. Fake private values use
   `@example.invalid` and `+91-000…` so leak tests can find them.
9. **Never commit secrets.** `.env`, `env`, `frontend/.env*.local`, `.vercel/` are git-ignored — keep it so.
10. In this demo the **role comes from the request body**; production must take it from the session.

## Commands
```bash
# run everything locally (DB in Docker on :5433, API, React UI) — on this dev machine ports 8000/5173 are taken
API_PORT=8010 python scripts/launch.py            # UI → http://127.0.0.1:5180 (always 127.0.0.1, not localhost)
python scripts/explain.py "fluter devlopers in lucknw"   # print every pipeline stage + the SQL

# tests
pytest -q                                          # 380+ tests; DB tests auto-skip without a database
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/commudle_safe_search pytest -q   # include DB tests
pytest -m integration                              # live Groq calls (costs tokens) — rarely

# lint / build
ruff check .
cd frontend && npx oxlint src && npm run build

# data
python -m seed.generate_dummy_dataset              # local dataset (deterministic)
python -m seed.load_dummy_dataset                  # (re)load into DATABASE_URL; --if-empty to only backfill

# deploy UI (API redeploys from GitHub on Render)
cd frontend && vercel deploy --prod
```

## Environment variables (backend)
| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local Postgres | `postgresql://` is auto-rewritten to psycopg2; an exported value beats `.env` |
| `GROQ_API_KEY` / `GROQ_MODEL` | — / `qwen/qwen3.8-27b` | free tier ≈200k tokens/day; 429 pauses the LLM, rules answer |
| `LLM_EXTRACTION_ENABLED`, `LLM_TIMEOUT_SECONDS`, `LLM_COOLDOWN_SECONDS` | true, 6, 60 | |
| `ENABLE_EMBEDDINGS` | true | needs `sentence-transformers` (~1.2 GB RAM per worker) |
| `ENABLE_TRACE` | false | returns the SQL trace for the Workflow page — demo only |
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | localhost list, none | production: `https://.*\.vercel\.app` |
| `RATE_LIMIT_SEARCH`, `RATE_LIMIT_WEB_ENRICH` | 30/60, 10/60 | per IP, per worker (in-memory) |
Frontend: `VITE_API_BASE` (absolute API URL in production; baked in at build time), `API_TARGET` (dev proxy).

## How to make common changes (and what must come with them)
| Change | Where | Must also |
|---|---|---|
| New technology / city | `KNOWN_TECHNOLOGIES` / `KNOWN_CITIES` in `app/config.py`; aliases in `app/fuzzy.py`; display name in both dataset generators | run `tests/test_fuzzy.py` (the everyday-word false-positive sweep must still pass) |
| New guard pattern | pattern lists in `app/validation.py` or `app/guard.py` | add the attack to `tests/data/adversarial_queries.json` **and** a legit look-alike to `tests/test_guard.py::OK` |
| New searchable field | it must be `info=PUBLIC` — which means `models.py` → **stop and ask a human** | |
| New ranking signal | `app/ranking.py::rank_results` + `effective_weights` | a unit test in `tests/test_ranking.py`; trace formula text in `main.py::_rank` |
| New response field | `app/schemas.py` + `app/main.py::_to_item` | `Results.jsx`, and an API test |
| Dataset change | generators in `seed/`; use a **separate RNG** for new data so existing records don't shift | regenerate, reload, DB ground-truth tests (`tests/test_db_integration.py`) |
| UI change | `frontend/src/*` | `npx oxlint src && npm run build`; check phone width (390 px) and `prefers-reduced-motion` |

## Definition of done
- `ruff check .` clean, `pytest -q` green **with** the DB (`DATABASE_URL` above), frontend lint + build green.
- Behaviour changes come with tests; security changes with an adversarial case *and* a false-positive check.
- For UI work, look at it: `node frontend/scripts/shot.mjs <url> out.png '[steps]'` (headless Chrome;
  supports `type`, `click`, `hover`, `wait`, `eval`, `slow`, `fail`, `width`).
- No secrets in the diff (`git grep -nE "gsk_|npg_"` on staged files).

## Gotchas an agent will hit on this machine (details in conflict.md)
- Ports 8000/5173/5432 belong to other projects → use 8010/5180/5433 and `127.0.0.1`.
- Long bash heredocs with quotes break in this Windows shell — write a script file and run it instead.
- Vite dependency cache goes stale after package changes → restart with `--force`.
- `lottie-react` 3.x changed its API — the app uses `lottie-web` directly.
- Render free tier sleeps; the UI retries for 75 s ("Waking up…").
