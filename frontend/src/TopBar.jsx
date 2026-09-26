import { PAGES, href } from './router'
import { PageIcon } from './pages/PageShell'
import './TopBar.css'

/** Brand + page navigation, shared by every route. */
export default function TopBar({ route }) {
  return (
    <header className="topbar">
      <a className="brand" href={href('/')} aria-label="Commudle Search — home">
        <span className="brand__mark" aria-hidden="true" />
        <span className="brand__name">Commudle</span>
        <span className="brand__sub">Search</span>
      </a>
      <nav className="topnav" aria-label="Pages">
        {PAGES.map((p) => (
          <a key={p.path} href={href(p.path)} className={`topnav__link${route === p.path ? ' is-active' : ''}`}
             aria-current={route === p.path ? 'page' : undefined} aria-label={p.label} title={p.label}>
            <PageIcon d={p.icon} />
            <span>{p.label}</span>
          </a>
        ))}
      </nav>
    </header>
  )
}
