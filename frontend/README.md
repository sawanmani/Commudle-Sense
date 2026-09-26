# Commudle Search — web UI (React + Vite)

The hero search experience for the Commudle Safe Search API: a glass pill with an iridescent hover
ring, "lift and search" icon, debounced suggestions, and results split into **On Commudle** and
**Other platforms** with "why shown" badges.

## Run

```bash
# 1. start the API (from the repo root) — e.g. python scripts/launch.py, or uvicorn app.main:app
# 2. start the UI
cd frontend
npm install
npm run dev                                   # http://127.0.0.1:5180, proxies /api → http://127.0.0.1:8000
API_TARGET=http://127.0.0.1:8010 npm run dev  # if your API runs on another port
```

The browser only talks to the Vite server; `/api/*` is proxied to FastAPI, so the backend needs no
CORS changes. For a deployed build set `VITE_API_BASE` to the API's URL (and add that origin to the
API's `CORS_ORIGINS`).

## Files

| File | What it does |
|---|---|
| `src/SearchHero.jsx` / `.css` | background, pill, hover ring, lift/shake, loading ring, suggestions, "searching as / near" context |
| `src/Results.jsx` / `.css` | result cards, blocked / clarifying / error banners |
| `src/api.js` | `/search` (JSON body) and `/autocomplete` client, friendly errors, https-only links |
| `scripts/shot.mjs` | headless-Chrome screenshot helper used to check each UI state |

Respects `prefers-reduced-motion` (no spin/lift/shake; search fires immediately) and is keyboard
accessible (Enter searches, Esc hides suggestions, visible focus rings, ARIA labels / live regions).
