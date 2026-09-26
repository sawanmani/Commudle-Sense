import { useEffect, useRef, useState } from 'react'
import SearchHero from './SearchHero'
import Results from './Results'
import DeepSearchLoader from './DeepSearchLoader'
import { getInsights, search, wakeUp } from './api'
import TopBar from './TopBar'
import { useRoute } from './router'
import Insights from './pages/Insights'
import Workflow from './pages/Workflow'
import Resources from './pages/Resources'

export default function App() {
  const [query, setQuery] = useState('')
  const [context, setContext] = useState({ auth_state: 'logged_out', city: null })
  const [loading, setLoading] = useState(false)
  const [loaderShown, setLoaderShown] = useState(false) // loader on screen (outlives `loading` briefly)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [lastQuery, setLastQuery] = useState('')
  const [waking, setWaking] = useState(false) // free hosting is waking the API up
  const inflight = useRef(null)
  const route = useRoute()
  const [stats, setStats] = useState(null)

  // live numbers for the trust strip (public aggregates; optional: the strip has a static fallback)
  useEffect(() => {
    wakeUp() // start waking a sleeping server immediately, before the first search
    const ctrl = new AbortController()
    getInsights({ signal: ctrl.signal })
      .then((d) => setStats({
        records: Object.values(d.entities).reduce((a, b) => a + b, 0),
        listings: d.external.total,
        platforms: d.external.platforms.length,
      }))
      .catch(() => {})
    return () => ctrl.abort()
  }, [])

  async function runSearch(q, ctx = context) {
    inflight.current?.abort()
    const ctrl = new AbortController()
    inflight.current = ctrl
    setLoading(true)
    setLoaderShown(true)
    setWaking(false)
    setError('')
    try {
      setData(await search(q, ctx, { signal: ctrl.signal, onWaking: () => setWaking(true) }))
      setLastQuery(q)
    } catch (e) {
      if (e.name !== 'AbortError') {
        setError(e.message)
        setData(null)
      }
    } finally {
      if (inflight.current === ctrl) {
        setLoading(false)
        setWaking(false)
      }
    }
  }

  // Clarifying-question options ("events", "speakers", …) refine the current query.
  function refine(option) {
    const q = `${query.trim()} ${option}`.trim()
    setQuery(q)
    runSearch(q)
  }

  if (route !== '/') {
    // search state above lives on, so "Back to search" returns to the same query and results
    const Page = { '/insights': Insights, '/workflow': Workflow, '/resources': Resources }[route]
    return (
      <main className="hero">
        <div className="hero__glow" aria-hidden="true" />
        <TopBar route={route} />
        <Page route={route} context={context} />
      </main>
    )
  }

  return (
    <main className="hero">
      <div className="hero__glow" aria-hidden="true" />
      <TopBar route={route} />
      <SearchHero
        query={query}
        onQueryChange={setQuery}
        onSearch={runSearch}
        loading={loading}
        compact={Boolean(data || error || loaderShown)}
        context={context}
        onContextChange={(next) => {
          setContext(next)
          if (lastQuery) runSearch(lastQuery, next) // switching role/city shows the difference immediately
        }}
        stats={stats}
      />
      <div className="stage">
        <DeepSearchLoader active={loading} onHidden={() => setLoaderShown(false)}
          label={waking ? 'Waking up the search server — the first search after a quiet spell takes up to a minute…' : undefined} />
        <div className={`stage__results${loaderShown ? ' is-waiting' : ''}`}>
          <Results data={data} error={error} onRefine={refine} query={lastQuery} />
        </div>
      </div>
    </main>
  )
}
