import { safeHttpsUrl } from './api'
import './Results.css'

const TYPE = { event: 'Event', hackathon: 'Hackathon', speaker: 'Speaker', community: 'Community', job: 'Job', lab: 'Lab', build: 'Project' }
const STATUS = { upcoming: 'Upcoming', today: 'Today', past: 'Past' }
const LEVEL = {
  online: 'Online — join from anywhere',
  relaxed_city: 'Other city, same tech',
  relaxed_tech: 'Same city, other tech',
}
const cityName = (c) => (c === 'remote' ? 'Online' : c.charAt(0).toUpperCase() + c.slice(1))

function LocalCard({ item }) {
  const broader = item.match_reasons.some((m) => m.startsWith('broader match'))
  const reasons = item.match_reasons.filter((m) => !m.startsWith('broader match'))
  return (
    <li className="card">
      <div className="card__top">
        <h3 className="card__title">{item.title}</h3>
        <span className="card__badges">
          <span className="type">{TYPE[item.entity_type] ?? item.entity_type}</span>
          {item.status && <span className={`badge badge--${item.status}`}>{STATUS[item.status]}</span>}
        </span>
      </div>
      <p className="card__meta">
        {[item.city && cityName(item.city), item.date && `${item.date_label === 'starts' ? '' : 'since '}${item.date}`]
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

export default function Results({ data, error, onRefine }) {
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
          <strong>Blocked by the safety filter.</strong> {reason} Private data such as emails, phone numbers,
          RSVPs and organiser analytics is never searchable.
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
