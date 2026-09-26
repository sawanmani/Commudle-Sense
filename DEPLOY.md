# Deploying Commudle Search

Three free services, ~15 minutes. Order matters (each step needs the previous one's URL).

| Part | Host | What runs there |
|---|---|---|
| Database | **Neon** | PostgreSQL + pgvector |
| API | **Render** (Docker) | FastAPI backend (`Dockerfile`, `render.yaml`) |
| Web UI | **Vercel** | React app in `frontend/` |

> Why not everything on Vercel: Vercel runs short-lived functions (500 MB max). The API needs an always-on
> process and a database, and its full dependency set is ~6 GB — that was the "exceeds 500 MB" build error.

## 1. Database — Neon
1. neon.tech → sign up → **New project** (any region near your users).
2. Copy the connection string: `postgresql://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require`
3. Load the synthetic data once, from your machine (repo root):
   ```bash
   # PowerShell:  $env:DATABASE_URL="<neon string>"; python -m seed.load_dummy_dataset
   DATABASE_URL="<neon string>" python -m seed.load_dummy_dataset
   ```
   Creates the tables, enables `vector`, loads 1,351 records and computes meaning vectors locally
   (if `sentence-transformers` is installed here) so the server never has to.

## 2. API — Render
1. render.com → sign up with GitHub → **New → Blueprint** → select `Commudle-Sense`. It reads `render.yaml`.
2. When asked, fill the two secrets:
   - `DATABASE_URL` = the Neon string
   - `GROQ_API_KEY` = your Groq key (optional — without it the rule-based extractor answers)
3. **Apply**. First build ~5 min. Then open `https://<name>.onrender.com/health` → `{"status":"ok",…}`
   and `/ready` → `{"ready":true,"database":"ok"}`.

Notes: the free plan (512 MB) runs without the embedding model (filters + ranking; measured ~90 MB RAM).
For semantic search use a 2 GB plan and build with `--build-arg EMBEDDINGS=true`. Free services sleep
after ~15 min idle — the first request afterwards takes ~30–60 s.

## 3. Web UI — Vercel
1. vercel.com → **Add New → Project** → import `Commudle-Sense` (branch `sankalp`).
2. **Root Directory: `frontend`** ← required (otherwise Vercel tries to build the Python API).
3. Framework preset **Vite** (build `npm run build`, output `dist` — auto-detected).
4. **Environment variable** `VITE_API_BASE` = `https://<name>.onrender.com` (no trailing slash).
5. **Deploy**. Open the Vercel URL and search.

CORS is already set: `render.yaml` allows any `https://*.vercel.app` origin (production and preview URLs).
Using a custom domain? Add it to `CORS_ORIGINS` on Render (comma-separated).

## Checklist if something fails
| Symptom | Fix |
|---|---|
| UI says "Can't reach the search service" | `VITE_API_BASE` wrong/missing → set it and **redeploy** (it is baked in at build time); or the Render service is asleep — open `/health` once |
| Browser console: CORS error | Your UI origin isn't `https://*.vercel.app` → add it to `CORS_ORIGINS` on Render |
| `/ready` → 503 | `DATABASE_URL` wrong, or the seed step (1.3) wasn't run |
| Workflow page: "trace switched off" | set `ENABLE_TRACE=true` on Render |

Local development is unchanged: `python scripts/launch.py`.
