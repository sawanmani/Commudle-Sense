# Conflicts & gotchas — and how they were resolved

A log of every clash hit while building and deploying this project, so nobody has to rediscover them.
Each entry: **symptom → cause → fix**.

## Live deployment (current)
| Part | URL / ID | Where it's configured |
|---|---|---|
| Web UI | https://commudle-search.vercel.app | Vercel project `commudle-search` (team `sankalp11`), env `VITE_API_BASE` |
| API | https://commudle-search-api.onrender.com | Render blueprint (`render.yaml`), env `DATABASE_URL`, `GROQ_API_KEY` |
| Database | Neon project, branch `production` | connection string lives only in Render's env — never in git |

Redeploy the UI: `cd frontend && vercel deploy --prod` (the GitHub repo belongs to another account, so Vercel
can't auto-deploy from git). The API redeploys from the `sankalp` branch on Render.

---

## Local machine: port clashes with other projects
| Symptom | Cause | Fix |
|---|---|---|
| `localhost:5173` opens **VoiceTrace**, not this app | VoiceTrace's Docker/WSL dashboard owns `5173` on `::1`; browsers resolve `localhost` → `::1` first | UI runs on **5180** (`strictPort`), always use **`127.0.0.1`** not `localhost` |
| API "ok" on :8000 but it's the wrong API | VoiceTrace backend owns **8000** | Run ours on **8010**: `API_PORT=8010 python scripts/launch.py --no-db`; UI with `API_TARGET=http://127.0.0.1:8010` |
| Postgres auth fails on 5432 | `kavach_postgres` (another project) owns **5432** | Our DB container on **5433** (`scripts/launch.py` default `DB_PORT=5433`) |
| Every request ~2 s slower on Windows | `localhost` tries IPv6 first | Use `127.0.0.1` everywhere (launcher, UI, scripts) |

## Deployment
| Symptom | Cause | Fix |
|---|---|---|
| Vercel: *"Total bundle size (5889 MB) exceeds 500 MB"* | Vercel found root `requirements.txt` and tried to ship the whole Python API (PyTorch) as one serverless function | UI only on Vercel (**Root Directory = `frontend`**); API on Render (Docker); DB on Neon. See `DEPLOY.md` |
| UI: *"Can't reach the search service"* on the live site | Render **free plan sleeps** after ~15 min idle; waking takes up to ~1 min and returns 502/503 meanwhile | UI now retries for 75 s showing "Waking up the search server…", and pings `/health` on page load. To avoid it entirely: paid plan, or an uptime pinger hitting `/health` every 10 min |
| Browser CORS error from the Vercel site | API only allowed listed origins | `CORS_ORIGIN_REGEX=https://.*\.vercel\.app` on Render (covers preview URLs); custom domains go in `CORS_ORIGINS` |
| Vercel can't connect the GitHub repo | Repo is owned by `sawanmani`; the Vercel account can't see it | Deploy with the CLI from `frontend/` (above), or give that Vercel account repo access |
| Render must pick the port | PaaS hosts assign `$PORT` | Dockerfile runs `uvicorn … --port ${PORT:-8000}` |
| `VITE_API_BASE` changed but site still calls old URL | Vite bakes env vars in **at build time** | Change it in Vercel, then **redeploy** |

## Backend
| Symptom | Cause | Fix |
|---|---|---|
| Searches hang 30 s then 503 (`QueuePool limit … reached`) | Sessions bound to `models.engine` (a lazy **proxy** object) took a new pooled connection per query and held them all | Bind sessions to `get_engine()` (real engine) — `app/main.py`, seed scripts. Regression test in `tests/test_db_integration.py` |
| `ModuleNotFoundError: psycopg` | SQLAlchemy 2.1 defaults `postgresql://` to psycopg3; we ship psycopg2 | `config.py` rewrites the URL to `postgresql+psycopg2://` |
| Exported `DATABASE_URL` ignored | `load_dotenv(override=True)` let `.env` win | An explicitly exported `DATABASE_URL` now wins over `.env` |
| All queries "blocked"/slow for minutes | Groq free tier: **200k tokens/day**, then HTTP 429 | Circuit breaker pauses the LLM for the provider's own "try again in …" time; the rule-based extractor answers meanwhile. Consider a paid Groq tier for demos |
| Can't add a column for audience / talks | `app/models.py` and `app/permissions.py` are **protected** (`[SACRED]`) | New tables in `app/models_extra.py` (`speaker_talks`, `record_audience`), filters applied in `query_builder.py` |
| "go" matched Django, "react" matched React Native | Substring `ILIKE` on tags | Whole-tag regex match (bound parameter) |
| Fuzzy matching mapped "ai" → Mumbai | `rapidfuzz.WRatio` is substring-friendly | `app/fuzzy.py`: edit-distance with length-scaled budget, aliases, ties rejected, ~200-word false-positive test |
| Web enrichment returned nothing | `duckduckgo_search` was renamed `ddgs` (old name silently returns []) | Use `ddgs` |
| Embedding model makes first request wait ~1 min | Model loads on first use | Loaded in the background at start-up; requests never wait (filters + ranking until ready). ~1.2 GB RAM per worker → free hosts run without it |

## Frontend
| Symptom | Cause | Fix |
|---|---|---|
| Build error *"Missing export default"* from `lottie-react` | lottie-react 3.x is a new API (named exports, new props) | Use `lottie-web` (light build) directly — `DeepSearchLoader.jsx` |
| Dev page blank, "504 Outdated Optimize Dep" | Vite's dependency cache stale after changing packages mid-session | Restart the dev server with `--force` |
| Streamlit: "cannot modify session_state after widget created" | Example buttons wrote the input's state directly | Button `on_click` callbacks |
| Fonts | Telma/Pally (ITF, Fontshare) — redistribution of font files in a public repo not confirmed as allowed | Loaded via Fontshare's official link, not committed |

## Git & secrets
| Symptom | Cause | Fix |
|---|---|---|
| `git push` 403 "denied to sankalpoff2005-sketch" | Cached GitHub credential for a different account | `git credential reject` for github.com, push again as the collaborator account |
| Groq key almost pushed | A file named `env` (no dot) wasn't git-ignored | Removed from the commit; `env` and `.env` ignored |
| Keys shown in chat/editor selections | Groq key and Neon password were pasted/selected during setup | **Rotate both** (Groq console; Neon → Roles → reset) and update Render's env |
| "LF will be replaced by CRLF" warnings | Windows line endings | Harmless |
