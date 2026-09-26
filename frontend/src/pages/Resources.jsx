import { useEffect, useState } from 'react'
import { API_BASE, getInsights } from '../api'
import PageShell from './PageShell'

// Real public listing pages — the same allow-listed hosts the API links to.
const PLATFORMS = [
  { name: 'Devfolio', url: 'https://devfolio.co/hackathons', what: 'Indian hackathons and project showcases' },
  { name: 'Devpost', url: 'https://devpost.com/hackathons', what: 'Global hackathons and submitted projects' },
  { name: 'Unstop', url: 'https://unstop.com/hackathons', what: 'Hackathons, competitions and jobs for students' },
  { name: 'HackerEarth', url: 'https://www.hackerearth.com/challenges/hackathon/', what: 'Hackathons, coding challenges and hiring' },
  { name: 'Hack2Skill', url: 'https://hack2skill.com/', what: 'Hackathons and skill tracks' },
  { name: 'DoraHacks', url: 'https://dorahacks.io/hackathon', what: 'Web3 and open-source hackathons' },
  { name: 'Commudle', url: 'https://www.commudle.com/', what: 'Developer communities, events and speakers' },
  { name: 'Luma', url: 'https://lu.ma/discover', what: 'Community meetups and events' },
]
const NEVER = ['Email addresses', 'Phone numbers', 'RSVP lists', 'Attendance logs', 'Form responses',
  'Private channels', 'Drafts', 'Organiser-only analytics & notes', 'Hackathon registrations', 'Job applicant lists']

export default function Resources({ route }) {
  const [counts, setCounts] = useState({})
  useEffect(() => {
    const ctrl = new AbortController()
    getInsights({ signal: ctrl.signal })
      .then((d) => setCounts(Object.fromEntries(d.external.platforms.map((p) => [p.name, p.count]))))
      .catch(() => {}) // counts are a nice-to-have on this page
    return () => ctrl.abort()
  }, [])

  return (
    <PageShell route={route} title="Resources"
               lead="Where the results come from, what you can use, and what this search will never show.">
      <section>
        <h2 className="section-title">Platforms we search</h2>
        <ul className="platforms">
          {PLATFORMS.map((p) => (
            <li key={p.name} className="panel platform-card">
              <div className="platform-card__top">
                <h3>{p.name}</h3>
                {counts[p.name] !== undefined && <span className="count">{counts[p.name]} listings</span>}
              </div>
              <p>{p.what}</p>
              <a className="ext-link" href={p.url} target="_blank" rel="noopener noreferrer">Visit {p.name} ↗</a>
            </li>
          ))}
        </ul>
        <p className="panel__note">
          Demo listings are synthetic, so each one links to the platform’s real public listing page to browse actual entries.
        </p>
      </section>

      <div className="grid2">
        <section className="panel">
          <h2 className="panel__title">For developers</h2>
          <ul className="links">
            <li><a href="/docs" target="_blank" rel="noopener noreferrer">Interactive API docs ↗</a><span>Try /search, /autocomplete, /insights live</span></li>
            <li><a href={`${API_BASE}/datasets/external-platforms.csv`} download>Download the other-platforms dataset (CSV)</a><span>700 synthetic listings, 33 columns</span></li>
            <li><a href="https://github.com/sawanmani/Commudle-Sense" target="_blank" rel="noopener noreferrer">Source code on GitHub ↗</a><span>FastAPI · PostgreSQL + pgvector · React</span></li>
            <li><a href="#/workflow">How a search works →</a><span>Trace any query stage by stage</span></li>
          </ul>
          <pre className="code">{`curl -X POST /search -H 'Content-Type: application/json' \\
  -d '{"query":"flutter events in Delhi","context":{"auth_state":"member","city":"delhi"}}'`}</pre>
        </section>

        <section className="panel">
          <h2 className="panel__title">Never searchable — for anyone</h2>
          <ul className="never">
            {NEVER.map((n) => <li key={n}>{n}</li>)}
          </ul>
          <p className="panel__note">
            This is enforced by the database query itself (only public columns are ever selected), not by asking the AI nicely.
            Organisers see the same public fields in search; organiser analytics live elsewhere.
          </p>
        </section>
      </div>

      <section className="panel">
        <h2 className="panel__title">Search tips</h2>
        <ul className="tips">
          <li><b>Name what you want</b> — events, speakers, hackathons, communities, jobs, labs or projects. Leave it out to see everything.</li>
          <li><b>Add a city or “near me”</b> — set your city above the results and “near me” uses it.</li>
          <li><b>Dates work</b> — “upcoming”, “this month”, “next month”, “in October”.</li>
          <li><b>Any language mix</b> — “Lucknow ke aas paas Android developers”, “दिल्ली में मशीन लर्निंग पर workshop”.</li>
          <li><b>Typos are fine</b> — “fluter devlopers in lucknw” still finds Flutter developers in Lucknow.</li>
          <li><b>“Spoke in”</b> — “speakers on Flutter who have spoken in Lucknow” looks at the events they actually spoke at.</li>
        </ul>
      </section>
    </PageShell>
  )
}
