import { PAGES, href } from '../router'
import './pages.css'


export function PageIcon({ d }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Common frame for the info pages: back link, title, sibling tabs. */
export default function PageShell({ route, title, lead, children }) {
  return (
    <div className="page">
      <nav className="page__nav" aria-label="Pages">
        <a className="back" href={href('/')}>← Back to search</a>
        <div className="tabs">
          {PAGES.map((p) => (
            <a key={p.path} href={href(p.path)} className={`tab${route === p.path ? ' is-active' : ''}`}
               aria-current={route === p.path ? 'page' : undefined}>
              <PageIcon d={p.icon} /> {p.label}
            </a>
          ))}
        </div>
      </nav>
      <header className="page__head">
        <h1>{title}</h1>
        {lead && <p>{lead}</p>}
      </header>
      {children}
    </div>
  )
}
