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

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, options)
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError('Can’t reach the search service. Is the API running?')
  }
  if (res.status === 429) {
    const retryAfter = Number(res.headers.get('retry-after')) || undefined
    throw new ApiError(`Too many searches — try again in ${retryAfter ?? 'a few'} seconds.`, { status: 429, retryAfter })
  }
  // 502/504 come from the proxy when FastAPI isn't running
  if (res.status === 502 || res.status === 504) throw new ApiError('Can’t reach the search service. Is the API running?', { status: res.status })
  if (res.status === 503) throw new ApiError('Search is temporarily unavailable. Please retry in a moment.', { status: 503 })
  if (res.status === 422) throw new ApiError('That search couldn’t be processed. Try rephrasing it.', { status: 422 })
  if (!res.ok) throw new ApiError(`Something went wrong (${res.status}).`, { status: res.status })
  return res.json()
}

/** POST /search — query travels in the JSON body, never the URL. */
export function search(query, context, { signal } = {}) {
  return request('/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, context, limit: 20 }),
    signal,
  })
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
