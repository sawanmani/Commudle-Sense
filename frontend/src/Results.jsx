import { safeHttpsUrl } from './api'
import './Results.css'

const TYPE = { event: 'Event', hackathon: 'Hackathon', speaker: 'Speaker', community: 'Community', job: 'Job', lab: 'Lab', build: 'Project' }
const ATTACK = {
  prompt_injection: 'prompt injection', role_escalation: 'role escalation', sql_injection: 'SQL injection',
  xss: 'script injection (XSS)', private_data: 'private-data request', suspicious: 'safety rule',
}
const DATE_PREFIX = { starts: '', created: 'since ', 'last talk': 'last talk ' }
const STATUS = { upcoming: 'Upcoming', today: 'Today', past: 'Past' }
const LEVEL = {
  online: 'Online — join from anywhere',
  relaxed_city: 'Other city, same tech',
  relaxed_tech: 'Same city, other tech',
}
const cityName = (c) => (c === 'remote' ? 'Online' : c.charAt(0).toUpperCase() + c.slice(1))

function LocalCard({ item }) {
  const broader = item.match_reasons.some((m) => m.startsWith('broader match'))
  const reasons = item.match_reasons.filter((m) => !m.startsWith('broader match') && !m.endsWith(' only'))
  return (
    <li className="card">
      <div className="card__top">
        <h3 className="card__title">{item.title}</h3>
        <span className="card__badges">
          <span className="type">{TYPE[item.entity_type] ?? item.entity_type}</span>
          {item.audience && (
            <span className={`audience audience--${item.audience}`} title="Only visible to signed-in members / organisers">
              🔒 {item.audience === 'members' ? 'Members only' : 'Organisers only'}
            </span>
          )}
          {item.status && <span className={`badge badge--${item.status}`}>{STATUS[item.status]}</span>}
        </span>
      </div>
      <p className="card__meta">
        {[item.city && cityName(item.city), item.date && `${DATE_PREFIX[item.date_label] ?? ''}${item.date}`]
          .filter(Boolean).join(' · ')}
      </p>
      {item.snippet && <p className="card__snippet">{item.snippet}</p>}
      <div className="card__why">
        <span className="why__label">Why shown</span>
        {reasons.map((r) => <span key={r} className="why">{r}</span>)}
        {broader && <span className="why why--broad">broader match</span>}
      </div>
    </li>
  )
}

function ExternalCard({ item }) {
  const url = safeHttpsUrl(item.redirect_url)
  return (
    <li className="card card--ext">
      <div className="card__top">
        <h3 className="card__title">{item.title}</h3>
        <span className="platform">{item.source_platform}</span>
      </div>
      <p className="card__meta">
        {[item.city && cityName(item.city), item.mode, item.start_date, item.status].filter(Boolean).join(' · ')}
      </p>
      {item.snippet && <p className="card__snippet">{item.snippet}</p>}
      <div className="card__why">
        {LEVEL[item.match_level] && <span className="why why--broad">{LEVEL[item.match_level]}</span>}
        {url && (
          <a className="ext-link" href={url} target="_blank" rel="noopener noreferrer">
            Open on {item.source_platform} ↗
          </a>
        )}
      </div>
    </li>
  )
}

export default function Results({ data, error, onRefine, query }) {
  if (error) {
    return (
      <div className="results">
        <div className="banner banner--error" role="alert">{error}</div>
      </div>
    )
  }
  if (!data) return null

  const { results, external_results: external, blocked, block_reason: reason, clarifying_question: question,
    clarification_options: options, notes } = data

  return (
    <div className="results" aria-live="polite">
      {blocked && !question && (
        <div className="banner banner--blocked" role="alert">
          <p className="block__head">
            <strong>⛔ Blocked — {ATTACK[data.block_category] ?? 'safety rule'}</strong>
          </p>
          <p>{reason}</p>
          <p className="block__foot">
            Stopped at the first stage: nothing reached the AI, the database or the web.{' '}
            {query && <a href={`#/workflow?q=${encodeURIComponent(query)}`}>See where it stopped →</a>}
          </p>
        </div>
      )}

      {question && (
        <div className="banner banner--ask">
          <p>{question}</p>
          {options?.length > 0 && (
            <div className="refine">
              {options.map((o) => (
                <button key={o} type="button" className="chip" onClick={() => onRefine(o)}>{o}</button>
              ))}
            </div>
          )}
        </div>
      )}

      {notes?.map((n) => <p key={n} className="note">{n}</p>)}

      {!question && options?.length > 0 && (
        <div className="refine refine--inline" aria-label="Narrow down">
          <span className="refine__label">Narrow down:</span>
          {options.map((o) => (
            <button key={o} type="button" className="chip" onClick={() => onRefine(o)}>{o}</button>
          ))}
        </div>
      )}

      {!blocked && (
        <>
          <section className="group" aria-labelledby="local-h">
            <h2 id="local-h" className="group__title">
              On Commudle <span className="count">{results.length}</span>
            </h2>
            {results.length ? (
              <ul className="cards">{results.map((r) => <LocalCard key={`${r.entity_type}-${r.id}`} item={r} />)}</ul>
            ) : (
              <p className="empty">Nothing on Commudle matched. See other platforms below.</p>
            )}
          </section>

          <section className="group" aria-labelledby="ext-h">
            <h2 id="ext-h" className="group__title">
              Other platforms <span className="count">{external.length}</span>
            </h2>
            <p className="group__sub">
              Devfolio · Devpost · Unstop · HackerEarth · Hack2Skill · DoraHacks · Commudle · Luma. Demo entries are
              synthetic — the link opens the platform’s real public listing so you can verify it.
            </p>
            {external.length ? (
              <ul className="cards">{external.map((r) => <ExternalCard key={r.id} item={r} />)}</ul>
            ) : (
              <p className="empty">No results from other platforms.</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}
