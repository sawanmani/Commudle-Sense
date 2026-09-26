import { useEffect, useState } from 'react'
import { getInsights } from '../api'
import PageShell from './PageShell'

const TYPE = { event: 'Events', hackathon: 'Hackathons', speaker: 'Speakers', community: 'Communities', job: 'Jobs', lab: 'Labs', build: 'Projects' }
const TECH = { ml: 'ML', genai: 'GenAI', aws: 'AWS', gcp: 'GCP', ios: 'iOS', nodejs: 'Node.js', graphql: 'GraphQL',
  devops: 'DevOps', fastapi: 'FastAPI', 'react-native': 'React Native', web3: 'Web3', vue: 'Vue.js', spring: 'Spring Boot' }
const nice = (s) => TECH[s] ?? (s === 'remote' ? 'Online' : s.charAt(0).toUpperCase() + s.slice(1))
const fmt = (n) => n.toLocaleString('en-IN')

function Stat({ label, value, hint }) {
  return (
    <div className="stat">
      <div className="stat__value">{value}</div>
      <div className="stat__label">{label}</div>
      {hint && <div className="stat__hint">{hint}</div>}
    </div>
  )
}

/** Single-series horizontal bars (one hue, value labelled at the bar end, table fallback). */
function BarList({ title, rows, unit = '', max }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.count))
  return (
    <section className="panel">
      <h2 className="panel__title">{title}</h2>
      <ul className="bars">
        {rows.map((r) => (
          <li key={r.name} className="bars__row" tabIndex={0} title={`${r.label ?? nice(r.name)}: ${fmt(r.count)}${unit}`}
              aria-label={`${r.label ?? nice(r.name)}: ${fmt(r.count)}${unit}`}>
            <span className="bars__label">{r.label ?? nice(r.name)}</span>
            <span className="bars__track">
              <span className="bars__fill" style={{ width: `${Math.max(1.5, (r.count / top) * 100)}%` }} />
            </span>
            <span className="bars__value">{fmt(r.count)}</span>
          </li>
        ))}
      </ul>
      <details className="as-table">
        <summary>View as table</summary>
        <table>
          <thead><tr><th scope="col">{title}</th><th scope="col">Count</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.name}><td>{r.label ?? nice(r.name)}</td><td>{fmt(r.count)}</td></tr>)}</tbody>
        </table>
      </details>
    </section>
  )
}

export default function Insights({ route }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const ctrl = new AbortController()
    getInsights({ signal: ctrl.signal }).then(setData).catch((e) => e.name !== 'AbortError' && setError(e.message))
    return () => ctrl.abort()
  }, [])

  return (
    <PageShell route={route} title="Insights"
               lead="What's searchable right now — counted live from public fields only. No names, contacts or private data are ever part of these numbers.">
      {error && <div className="banner banner--error" role="alert">{error}</div>}
      {!data && !error && <p className="loading-text">Loading insights…</p>}
      {data && (
        <>
          <div className="stats">
            <Stat label="Searchable records on Commudle" value={fmt(Object.values(data.entities).reduce((a, b) => a + b, 0))}
                  hint={`${Object.keys(data.entities).length} types`} />
            <Stat label="Events & hackathons in the next 30 days"
                  value={fmt(data.upcoming.events_next_30_days + data.upcoming.hackathons_next_30_days)}
                  hint={`${data.upcoming.events_next_30_days} events · ${data.upcoming.hackathons_next_30_days} hackathons`} />
            <Stat label="Cities covered" value={data.cities.length} hint="including Online" />
            <Stat label="Listings from other platforms" value={fmt(data.external.total)} hint={`${data.external.platforms.length} platforms`} />
          </div>

          <div className="grid2">
            <BarList title="Records by type" rows={Object.entries(data.entities).sort((a, b) => b[1] - a[1])
              .map(([name, count]) => ({ name, count, label: TYPE[name] }))} />
            <BarList title="Most-tagged technologies" rows={data.top_technologies} />
            <BarList title="Upcoming events & hackathons by city" rows={data.upcoming_by_city} />
            <BarList title="Other platforms" rows={data.external.platforms.map((p) => ({ ...p, label: p.name }))} />
          </div>

          <section className="panel panel--safety">
            <h2 className="panel__title">Safety</h2>
            <div className="stats stats--compact">
              <Stat label="Blocked or unclear requests (all time)" value={fmt(data.safety.blocked_total)} />
              <Stat label="In the last 24 hours" value={fmt(data.safety.blocked_last_24h)} />
            </div>
            {data.safety.by_reason.length > 0 && (
              <ul className="reasons">
                {data.safety.by_reason.map((r) => (
                  <li key={r.name}><span>{r.name}</span><strong>{fmt(r.count)}</strong></li>
                ))}
              </ul>
            )}
            <p className="panel__note">Counts come from the audit log by reason only — the text of blocked searches is never shown.</p>
          </section>

          <section className="panel runtime">
            <h2 className="panel__title">Right now</h2>
            <dl>
              <div><dt>Query understanding</dt><dd>{data.runtime.llm_extraction === 'available' ? 'LLM (Groq) + rules' : 'Rules (LLM paused)'}</dd></div>
              <div><dt>Semantic search</dt><dd>{data.runtime.semantic_search}</dd></div>
              <div><dt>Search rate limit</dt><dd>{data.runtime.rate_limit_search.replace('/', ' per ')} s per visitor</dd></div>
              <div><dt>Updated</dt><dd>{new Date(data.generated_at).toLocaleTimeString()}</dd></div>
            </dl>
          </section>
        </>
      )}
    </PageShell>
  )
}
