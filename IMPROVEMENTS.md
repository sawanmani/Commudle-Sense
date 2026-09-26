# IMPROVEMENTS.md — what to build next

A prioritised backlog for improving Commudle Search. Every item says **why**, **where** (files), and
**done when** (so an AI assistant or a teammate can pick it up without guessing). Follow the rules in
[`AGENTS.md`](AGENTS.md); log any new clash you hit in [`conflict.md`](conflict.md).

**Priorities** — **P0** fix soon (risk or correctness) · **P1** clear product/PS value · **P2** polish & scale.
Tick items off by moving them to "Done" at the bottom with the commit hash.

---

## P0 — fix soon

### 1. Rotate the secrets that were exposed during setup
- **Why:** the Groq key and the Neon password appeared in chat/editor selections.
- **Where:** Groq console; Neon → Roles → reset password; update Render env (`GROQ_API_KEY`, `DATABASE_URL`).
- **Done when:** old values rejected; `/ready` on Render still `{"ready":true}`.

### 2. Take the role from a real session, not the request body
- **Why:** `context.auth_state` is client-supplied (fine for a demo, not for production) — anyone can claim
  "organiser" and list organisers-only records.
- **Where:** `app/main.py` (search dependency), `app/schemas.py::RequesterContext`, `frontend/src/App.jsx`.
- **Done when:** role comes from a verified token (e.g. Commudle session/JWT) with the body value ignored;
  test: a forged `"auth_state":"organiser"` without a token sees only public listings.

### 3. Keep the blocked-attempt log across deploys
- **Why:** it's a file under `logs/`; Render's disk is temporary, so every redeploy resets the Insights
  "Safety" numbers — and a JSONL file doesn't work across several workers/instances either.
- **Where:** `app/logging_utils.py`, `app/insights.py::_safety`, new table in `app/models_extra.py`.
- **Done when:** attempts stored in Postgres (reason, category, role, timestamp — **no query text** in anything
  exposed); Insights reads counts from the table; a restart doesn't reset them.

### 4. Refresh `docs/ARCHITECTURE.md`
- **Why:** it still describes the original 5-stage pipeline (no guard, fuzzy matching, row audience,
  all-types search, broadening, external catalog, React UI).
- **Where:** `docs/ARCHITECTURE.md` (source of truth for the diagram: the pipeline table in `AGENTS.md`).
- **Done when:** the doc matches `scripts/explain.py` output stage for stage.

---

## P1 — clear value

### 5. Hybrid (meaning) search for hackathons, communities, jobs, labs, projects
- **Why:** only events and speakers have embeddings (`models.py` is protected, so no new column there).
- **Where:** new `record_embeddings(entity, record_id, embedding vector(384))` in `app/models_extra.py`;
  `seed/load_dummy_dataset.py` fills it; `app/query_builder.py` joins it for similarity.
- **Done when:** trace step 5 shows "used" for all 7 types; a DB test like
  `test_semantic_search_ranks_by_meaning` for hackathons passes.

### 6. Shared rate limits and caches (Redis)
- **Why:** limiter, LLM cache and LLM pause are per worker process → real limit = N × configured.
- **Where:** `app/ratelimit.py`, `app/extraction.py` (cache + breaker).
- **Done when:** with 2 workers, 31 requests/min from one IP → the 31st gets 429; cache hits across workers.

### 7. No cold starts in the demo
- **Why:** Render free tier sleeps; first search after idle waits up to a minute.
- **Where:** hosting config (paid plan / Fly.io min 1 machine) or an uptime pinger on `/health` every 10 min.
- **Done when:** first search after 30 min idle answers in < 2 s.

### 8. Frontend tests in CI
- **Why:** the UI is verified by screenshots by hand; nothing stops a regression.
- **Where:** `frontend/` — Vitest for `api.js` (retry/wake logic) and components; a Playwright smoke test
  (search, attack blocked, role badges); `.github/workflows/ci.yml`.
- **Done when:** CI runs them on every push and fails on a broken search flow.

### 9. Extraction quality scoreboard
- **Why:** we know the rules pass 20/20 normal queries, but not how the LLM vs rules compare at scale.
- **Where:** `tests/data/eval_queries.json` (100+ labelled queries incl. Hindi/Hinglish/typos), `scripts/eval_extraction.py`.
- **Done when:** a report with per-field accuracy (entity, tech, city, dates) for `llm` and `rules`; tracked in CI.

### 10. Honest "Other platforms" data
- **Why:** those 700 listings are synthetic (clearly labelled) and link to platform listing pages.
- **Where:** `app/external_catalog.py` + a fetcher per platform **only where the platform's API/ToS allows it**.
- **Done when:** at least one platform shows real, current listings with deep links; synthetic ones removed or tagged.

### 11. Pagination
- **Where:** `limit`/`offset` (or cursor) in `app/schemas.py::SearchRequest` → `query_builder.py`; "Load more" in `Results.jsx`.
- **Done when:** a search with 50+ matches can be paged without duplicates (DB test).

---

## P2 — polish & scale

| # | Item | Where | Done when |
|---|---|---|---|
| 12 | Slimmer API image (split `requirements-api.txt` — the API image carries Streamlit) | `requirements*.txt`, `Dockerfile` | image < 500 MB, same tests pass |
| 13 | Dependency & secret scanning (`pip-audit`, `npm audit`, gitleaks) | `.github/workflows/ci.yml` | CI fails on known-vulnerable deps or a committed key |
| 14 | Observability: structured JSON logs with the request id, error tracking | `app/main.py` middleware, `app/logging_utils.py` | an error in prod is findable by `X-Request-ID` |
| 15 | Hindi UI (not just Hindi queries) | `frontend/src` strings → small i18n map | language toggle; no layout breaks at 390 px |
| 16 | Accessibility audit (axe) + keyboard-only pass | Playwright + axe in CI | zero serious axe violations on all 4 pages |
| 17 | Second-opinion injection classifier next to the regex guard | `app/guard.py` | adversarial suite + false-positive suite both still pass; new obfuscations caught |
| 18 | Saved searches / alerts for new matching events | new endpoints + table | a member gets matches for a saved query |
| 19 | "Did you mean" for unknown words (suggest nearest allow-list term instead of silently dropping) | `app/validation.py`, `Results.jsx` | "kotln jobs" shows "Did you mean Kotlin?" |
| 20 | Lottie loader weight (80 KB JSON + 47 KB engine) → dotLottie or CSS fallback on slow networks | `DeepSearchLoader.jsx` | loader chunk < 40 KB gz |

---

## Done
| Item | Commit |
|---|---|
| Role-based row visibility (members / organisers) | `b1be2e1` |
| Attack demo + named block categories | `b1be2e1` |
| Recent-activity ranking for speakers | `b1be2e1` |
| Deployment (Neon + Render + Vercel) | `b0cb9dc` |
| Survive sleeping free-tier API (retry + wake ping) | `4ccf28d` |
