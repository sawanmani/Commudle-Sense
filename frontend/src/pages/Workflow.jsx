import { useEffect, useRef, useState } from 'react'
import { traceSearch } from '../api'
import PageShell from './PageShell'
import { hashParam } from '../router'

// The pipeline, in order. `key` is the stage number the API's trace uses.
const STAGES = [
  { key: '1', name: 'Input', file: 'main.py', what: 'Your words arrive in the request body (never the URL), with who is asking: guest, member or organiser, and their city.' },
  { key: '2', name: 'Safety guard', file: 'guard.py', what: 'Runs before anything else. Unicode-normalises the text so invisible characters can’t hide tricks, then blocks prompt injection, SQL, role-escalation and private-data requests — in English, Hindi and Hinglish. A blocked search never reaches the model, the database or the web.' },
  { key: '3', name: 'Understand', file: 'extraction.py · fallback_extraction.py', what: 'An LLM fills a fixed JSON form (type, technologies, city, dates…). If it is paused or unsure, deterministic rules do it — typo-tolerant, so “fluter devlopers in lucknw” still works. The model has no database access.' },
  { key: '4', name: 'Validate', file: 'validation.py · fuzzy.py', what: 'Every value must map onto a closed allow-list (31 technologies, 15 cities, 7 types). Typos and aliases are corrected (Bengaluru → bangalore); anything else is dropped, never widened.' },
  { key: '5', name: 'Choose & embed', file: 'main.py · ranking.py', what: 'Picks what to search — one type, or every type when you didn’t name one — and turns the text into a meaning vector for semantic matching.' },
  { key: '6', name: 'Permission-checked SQL', file: 'query_builder.py · permissions.py', what: 'Builds a parameterised query that selects PUBLIC columns only. Emails, phones, RSVPs, attendance, form responses, drafts and organiser analytics are structurally unselectable, for every role.' },
  { key: '7', name: 'Rank', file: 'ranking.py', what: 'Upcoming first (soonest first) for events and hackathons, blended with meaning similarity and activity. No exact match? The search is re-run with one filter removed and labelled “broader match”.' },
  { key: '8', name: 'Clean stored text', file: 'validation.py', what: 'Database text is untrusted too: any title or description that looks like an injection payload is replaced before it reaches you.' },
  { key: '9', name: 'Other platforms', file: 'external_catalog.py', what: 'The same validated filters run over listings from Devfolio, Devpost, Unstop, HackerEarth, Hack2Skill, DoraHacks, Commudle and Luma. Links must be https on an allow-listed host.' },
]
const EXAMPLES = ['fluter developers in lucknw', 'frontend', 'upcoming hackathons in Delhi', "'; DROP TABLE users; --"]

function StageDetail({ step }) {
  if (!step) return null
  const shown = (o) => Object.fromEntries(Object.entries(o || {}).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length)))
  return (
    <div className="trace">
      <span className={`trace__status trace__status--${/BLOCK/.test(step.status) ? 'bad' : /skip|nothing|ask/.test(step.status) ? 'muted' : 'ok'}`}>
        {step.status}
      </span>
      {step.note && <p className="trace__note">{step.note}</p>}
      {step.produced_by && <p className="trace__kv"><b>Produced by</b> {step.produced_by}</p>}
      {step.reason && <p className="trace__kv"><b>Reason</b> {step.reason}</p>}
      {step.dropped?.length > 0 && <p className="trace__kv"><b>Dropped</b> {step.dropped.join(', ')}</p>}
      {step.validated_intent && <pre className="code">{JSON.stringify(shown(step.validated_intent), null, 2)}</pre>}
      {step.raw_intent && !step.validated_intent && <pre className="code">{JSON.stringify(shown(step.raw_intent), null, 2)}</pre>}
      {step.sql && (
        <>
          <pre className="code code--sql">{step.sql}</pre>
          <p className="trace__kv"><b>Bound parameters</b> {JSON.stringify(step.params)}</p>
          <p className="trace__kv"><b>Selected</b> {step.allowed_columns?.join(', ')}</p>
          <p className="trace__kv trace__kv--hidden"><b>Never selectable</b> {step.hidden_columns?.map((h) => h.column).join(', ') || 'none'}</p>
        </>
      )}
      {step.per_type_rows && <p className="trace__kv"><b>Rows per type</b> {Object.entries(step.per_type_rows).map(([k, v]) => `${k} ${v}`).join(' · ')}</p>}
      {step.rows_returned !== undefined && !step.sql && <p className="trace__kv"><b>Rows</b> {step.rows_returned}</p>}
      {step.formula && <p className="trace__kv"><b>Score</b> {step.formula}</p>}
      {step.hits !== undefined && <p className="trace__kv"><b>Listings found</b> {step.hits}</p>}
      {step.showing && <p className="trace__kv"><b>Broadened to</b> {step.showing}</p>}
    </div>
  )
}

export default function Workflow({ route, context }) {
  const [q, setQ] = useState('')
  const [trace, setTrace] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const inflight = useRef(null)
  const deepLink = useRef(hashParam('q'))

  // "See where it stopped →" links here with ?q=… — trace it straight away
  useEffect(() => {
    if (deepLink.current) run(deepLink.current)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function run(text) {
    const query = (text ?? q).trim()
    if (!query) return
    setQ(query)
    inflight.current?.abort()
    const ctrl = new AbortController()
    inflight.current = ctrl
    setBusy(true)
    setMsg('')
    try {
      const j = await traceSearch(query, context, { signal: ctrl.signal })
      if (!j.trace) {
        setTrace(null)
        setMsg('This server has the step-by-step trace switched off (ENABLE_TRACE=false). The launcher and Docker turn it on for demos.')
      } else {
        const byStage = {}
        for (const s of j.trace) byStage[s.stage.split('.')[0].replace(/b$/, '')] ??= s
        for (const s of j.trace) if (/^6b/.test(s.stage)) byStage['7b'] = s
        setTrace({ byStage, blocked: j.blocked, count: j.results.length, ext: j.external_results.length })
      }
    } catch (e) {
      if (e.name !== 'AbortError') setMsg(e.message)
    } finally {
      if (inflight.current === ctrl) setBusy(false)
    }
  }

  return (
    <PageShell route={route} title="How a search works"
               lead="Nine stages, every one enforced in code. Trace any query below to watch what each stage did with it — including the exact SQL.">
      <section className="panel tracer">
        <form className="tracer__form" onSubmit={(e) => { e.preventDefault(); run() }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Try: fluter developers in lucknw"
                 aria-label="Query to trace" maxLength={500} />
          <button type="submit" className="btn" disabled={busy}>{busy ? 'Tracing…' : 'Trace it'}</button>
        </form>
        <div className="tracer__examples">
          {EXAMPLES.map((e) => <button key={e} type="button" className="chip" onClick={() => run(e)}>{e}</button>)}
        </div>
        {msg && <p className="note">{msg}</p>}
        {trace && (
          <p className="tracer__summary" role="status">
            {trace.blocked ? 'Blocked — it stopped at the safety guard.' : `${trace.count} Commudle results · ${trace.ext} from other platforms.`}
          </p>
        )}
      </section>

      <ol className="flow">
        {STAGES.map((s) => {
          const step = trace?.byStage[s.key]
          const state = !trace ? '' : step ? (/BLOCK/.test(step.status) ? ' is-blocked' : ' is-done') : ' is-skipped'
          return (
            <li key={s.key} className={`flow__step${state}`}>
              <div className="flow__dot" aria-hidden="true">{s.key}</div>
              <div className="flow__body">
                <h3>{s.name} <code>{s.file}</code></h3>
                <p>{s.what}</p>
                <StageDetail step={step} />
                {s.key === '7' && <StageDetail step={trace?.byStage['7b']} />}
                {trace && !step && <p className="trace__note">Not reached{trace.blocked ? ' — the search was stopped earlier.' : '.'}</p>}
              </div>
            </li>
          )
        })}
      </ol>
    </PageShell>
  )
}
