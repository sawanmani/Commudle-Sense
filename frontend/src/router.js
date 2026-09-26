import { useEffect, useState } from 'react'

// Tiny hash router: #/insights, #/workflow, #/resources. No dependency, works on any static host.
export const ROUTES = ['/', '/insights', '/workflow', '/resources']

const current = () => {
  const path = window.location.hash.replace(/^#/, '') || '/'
  return ROUTES.includes(path) ? path : '/'
}

export function useRoute() {
  const [route, setRoute] = useState(current)
  useEffect(() => {
    const onChange = () => {
      setRoute(current())
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export const href = (path) => `#${path}`

// The info pages (label + icon path), used by the search row buttons and the page tabs.
export const PAGES = [
  { path: '/insights', label: 'Insights', icon: 'M4 19V9m6 10V5m6 14v-7m4 7H2' },
  { path: '/workflow', label: 'Workflow', icon: 'M5 6h5v5H5zM14 13h5v5h-5zM10 8.5h4a2 2 0 012 2V13' },
  { path: '/resources', label: 'Resources', icon: 'M4 5a2 2 0 012-2h9l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2zM14 3v5h5M8 13h8M8 17h5' },
]
