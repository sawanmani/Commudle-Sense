import { href } from '../router'
import './pages.css'


export function PageIcon({ d }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Common frame for the info pages: back link and title (navigation lives in the top bar). */
export default function PageShell({ title, lead, children }) {
  return (
    <div className="page">
      <a className="back" href={href('/')}>← Back to search</a>
      <header className="page__head">
        <h1>{title}</h1>
        {lead && <p>{lead}</p>}
      </header>
      {children}
    </div>
  )
}
