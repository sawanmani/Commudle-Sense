import { useRef, useState } from 'react'
import SearchHero from './SearchHero'
import Results from './Results'
import DeepSearchLoader from './DeepSearchLoader'
import { search } from './api'
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
  const inflight = useRef(null)
  const route = useRoute()

  async function runSearch(q) {
    inflight.current?.abort()
    const ctrl = new AbortController()
    inflight.current = ctrl
    setLoading(true)
    setLoaderShown(true)
    setError('')
    try {
      setData(await search(q, context, { signal: ctrl.signal }))
    } catch (e) {
      if (e.name !== 'AbortError') {
        setError(e.message)
        setData(null)
      }
    } finally {
      if (inflight.current === ctrl) setLoading(false)
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
        <Page route={route} context={context} />
      </main>
    )
  }

  return (
    <main className="hero">
      <div className="hero__glow" aria-hidden="true" />
      <SearchHero
        query={query}
        onQueryChange={setQuery}
        onSearch={runSearch}
        loading={loading}
        compact={Boolean(data || error || loaderShown)}
        context={context}
        onContextChange={setContext}
      />
      <div className="stage">
        <DeepSearchLoader active={loading} onHidden={() => setLoaderShown(false)} />
        <div className={`stage__results${loaderShown ? ' is-waiting' : ''}`}>
          <Results data={data} error={error} onRefine={refine} />
        </div>
      </div>
    </main>
  )
}
