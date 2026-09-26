// Thin client for the FastAPI backend. In dev, Vite proxies /api → FastAPI (see vite.config.js), so the
// browser talks to a single origin and the backend's CORS settings stay untouched.
const BASE = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  constructor(message, { status, retryAfter } = {}) {
    super(message)
    this.status = status
    this.retryAfter = retryAfter
  }
}

// Free hosting (Render) puts the API to sleep when idle; waking takes up to ~1 minute, during which the
// request fails or the host answers 502/503/504. Those are retried until WAKE_BUDGET_MS instead of failing.
const WAKE_BUDGET_MS = 75_000
const RETRYABLE = new Set([502, 503, 504])

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}

async function request(path, options = {}, { onWaking } = {}) {
  const deadline = Date.now() + WAKE_BUDGET_MS
  for (let attempt = 0; ; attempt++) {
    let res
    try {
      res = await fetch(`${BASE}${path}`, options)
    } catch (e) {
      if (e.name === 'AbortError') throw e
      res = null // network error: server asleep / starting, or unreachable
    }
    if ((res === null || RETRYABLE.has(res.status)) && Date.now() < deadline) {
      onWaking?.()
      await sleep(Math.min(2000 + attempt * 1500, 8000), options.signal)
      continue
    }
    if (res === null || res.status === 502 || res.status === 504) {
      throw new ApiError('Can’t reach the search service right now. It may still be starting — please try again in a moment.')
    }
    return handle(res)
  }
}

async function handle(res) {
  if (res.status === 429) {
    const retryAfter = Number(res.headers.get('retry-after')) || undefined
    throw new ApiError(`Too many searches — try again in ${retryAfter ?? 'a few'} seconds.`, { status: 429, retryAfter })
  }
  if (res.status === 503) throw new ApiError('Search is temporarily unavailable. Please retry in a moment.', { status: 503 })
  if (res.status === 422) throw new ApiError('That search couldn’t be processed. Try rephrasing it.', { status: 422 })
  if (!res.ok) throw new ApiError(`Something went wrong (${res.status}).`, { status: res.status })
  return res.json()
}

/** POST /search — query travels in the JSON body, never the URL. */
export function search(query, context, { signal, onWaking } = {}) {
  return request('/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, context, limit: 20 }),
    signal,
  }, { onWaking })
}

/** Fire-and-forget ping so a sleeping server starts waking while the visitor is still reading/typing. */
export function wakeUp() {
  fetch(`${BASE}/health`).then((r) => r.text()).catch(() => {}) // read the body so the request completes
}

/** GET /autocomplete — suggestions come from the backend's safe template pool. */
export async function autocomplete(q, city, { signal } = {}) {
  const params = new URLSearchParams({ q })
  if (city) params.set('city', city)
  const data = await request(`/autocomplete?${params}`, { signal })
  return Array.isArray(data?.suggestions) ? data.suggestions : []
}

/** Only ever link to https URLs (the backend already allow-lists hosts; this is belt and braces). */
export function safeHttpsUrl(url) {
  try {
    const u = new URL(url)
    return u.protocol === 'https:' ? u.href : null
  } catch {
    return null
  }
}

/** GET /insights — public aggregate counts only. */
export function getInsights({ signal } = {}) {
  return request('/insights', { signal })
}

/** POST /search with debug=true — returns the step-by-step trace when the server allows it (ENABLE_TRACE). */
export function traceSearch(query, context, { signal } = {}) {
  return request('/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, context, limit: 10, debug: true }),
    signal,
  })
}

export const API_BASE = BASE
/** Where the API's own pages live (/docs): same origin in dev (proxied), the API host in production. */
export const API_ORIGIN = BASE.startsWith('http') ? BASE.replace(/\/$/, '') : ''
