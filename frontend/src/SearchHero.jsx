import { useEffect, useRef, useState } from 'react'
import { autocomplete } from './api'
import { PageIcon } from './pages/PageShell'
import { PAGES, href } from './router'
import './SearchHero.css'

const CITIES = ['lucknow', 'delhi', 'bangalore', 'mumbai', 'pune', 'hyderabad', 'chennai', 'kolkata',
  'noida', 'gurgaon', 'ahmedabad', 'jaipur', 'indore', 'chandigarh']
const ROLES = [
  { value: 'logged_out', label: 'Guest' },
  { value: 'member', label: 'Member' },
  { value: 'organiser', label: 'Organiser' },
]
const title = (s) => s.charAt(0).toUpperCase() + s.slice(1)

function SearchIcon() {
  return (
    <svg className="disc__icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M16 16l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

/** Debounced suggestions from GET /autocomplete. Stale requests are aborted. */
function useSuggestions(query, city, enabled) {
  const [items, setItems] = useState([])
  const q = query.trim()
  const active = enabled && q.length >= 2
  useEffect(() => {
    if (!active) return
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      autocomplete(q, city, { signal: ctrl.signal })
        .then((s) => setItems(s.filter((x) => x.toLowerCase() !== q.toLowerCase()).slice(0, 6)))
        .catch(() => setItems([])) // suggestions are optional: fail quietly
    }, 300)
    return () => {
      clearTimeout(t)
      ctrl.abort()
    }
  }, [q, city, active])
  return active ? items : []
}

/**
 * Hero search pill. Emits onSearch(query) — it never calls /search itself.
 * Click the icon (or Enter, or a suggestion): with text → icon lifts + disc pulses, then onSearch fires;
 * empty → the pill shakes and nothing is emitted. While `loading`, the disc's ring spins.
 */
export default function SearchHero({ query, onQueryChange, onSearch, loading = false, compact = false, context, onContextChange }) {
  const [anim, setAnim] = useState('idle') // idle | lift | shake
  const [hint, setHint] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(true)
  const inputRef = useRef(null)
  const pending = useRef('')
  const suggestions = useSuggestions(query, context.city, showSuggestions && !loading)

  function run(q) {
    q = q.trim()
    if (anim !== 'idle' || loading) return
    if (!q) {
      setHint('Type something to search first.')
      setAnim('shake')
      inputRef.current?.focus()
      return
    }
    setHint('')
    setShowSuggestions(false)
    pending.current = q
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      onSearch(q) // no animation to wait for
      return
    }
    setAnim('lift')
  }

  function onAnimationEnd(e) {
    if (anim === 'lift' && e.animationName === 'icon-lift') {
      setAnim('idle')
      onSearch(pending.current)
    } else if (anim === 'shake' && e.animationName === 'pill-shake') {
      setAnim('idle')
    }
  }

  const pillClass = ['pill', anim === 'shake' && 'is-shaking', loading && 'is-loading'].filter(Boolean).join(' ')

  return (
    <section className={`hero__center${compact ? ' is-compact' : ''}`}>
      <h1 className="hero__title">Find your people &amp; events</h1>
      <p className="hero__subtitle">Communities, speakers, events, hackathons, labs and jobs — ask the way you talk.</p>

      <form
        className={pillClass}
        role="search"
        aria-busy={loading}
        onSubmit={(e) => {
          e.preventDefault()
          run(query)
        }}
        onAnimationEnd={onAnimationEnd}
      >
        <button type="submit" className={`disc${anim === 'lift' ? ' is-lifting' : ''}`} aria-label="Search" disabled={loading}>
          <SearchIcon />
        </button>
        <input
          ref={inputRef}
          className="pill__input"
          type="search"
          value={query}
          onChange={(e) => {
            onQueryChange(e.target.value)
            setShowSuggestions(true)
            if (hint) setHint('')
          }}
          onKeyDown={(e) => e.key === 'Escape' && setShowSuggestions(false)}
          placeholder="Search in English, Hindi or Hinglish…"
          aria-label="Search Commudle"
          aria-describedby="search-hint"
          autoComplete="off"
          spellCheck="false"
          maxLength={500}
        />
      </form>
      <p id="search-hint" className="hero__hint" aria-live="polite">{hint}</p>

      {suggestions.length > 0 && (
        <ul className="chips" aria-label="Suggestions">
          {suggestions.map((s) => (
            <li key={s}>
              <button
                type="button"
                className="chip"
                onClick={() => {
                  onQueryChange(s)
                  run(s)
                }}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="context">
        <label>
          <span>Searching as</span>
          <select value={context.auth_state} onChange={(e) => onContextChange({ ...context, auth_state: e.target.value })}>
            {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
        <label>
          <span>near</span>
          <select value={context.city ?? ''} onChange={(e) => onContextChange({ ...context, city: e.target.value || null })}>
            <option value="">any city</option>
            {CITIES.map((c) => <option key={c} value={c}>{title(c)}</option>)}
          </select>
        </label>
        <span className="context__divider" aria-hidden="true" />
        <nav className="context__nav" aria-label="More">
          {PAGES.map((p) => (
            <a key={p.path} className="navbtn" href={href(p.path)}>
              <PageIcon d={p.icon} /> {p.label}
            </a>
          ))}
        </nav>
      </div>
    </section>
  )
}
