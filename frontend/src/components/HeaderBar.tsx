import type { InspectionsResponse } from '../api/types'
import { ROUTE_HASH, type Route } from '../router'
import type { Theme } from '../theme/useTheme'

interface Props {
  route: Route
  product: string | null
  session: InspectionsResponse | null
  theme: Theme
  onToggleTheme: () => void
}

const NAV: { route: Route; label: string }[] = [
  { route: 'map', label: 'Wafer map' },
  { route: 'layouts', label: 'Layouts' },
]

export function HeaderBar({ route, product, session, theme, onToggleTheme }: Props) {
  return (
    <header className="top-header">
      <div>
        <h1 className="app-title">Spring Wafer Intelligence</h1>
        <div className="app-subtitle">
          {route === 'layouts'
            ? 'Layouts · product coordinate references for the wafer map'
            : 'Product-based coordinate registration · Individual inspection · Multi-wafer spatial signatures'}
        </div>
      </div>
      <nav className="nav-links" aria-label="Pages">
        {NAV.map((n) => (
          <a key={n.route} href={ROUTE_HASH[n.route]} aria-current={route === n.route ? 'page' : undefined}>
            {n.label}
          </a>
        ))}
      </nav>
      <div className="header-spacer" />
      {route === 'map' && product && (
        <span className="dataset-pill" title={`Product ${product}`}>
          {product}
          {session ? ` · ${session.wafers.length} wafer${session.wafers.length === 1 ? '' : 's'}` : ''}
        </span>
      )}
      <span className="status-badge">Notch ↓ (assumed)</span>
      {route === 'map' && session && (
        <span className="status-badge" data-testid="status-model-badge">
          {session.status_model === 'defect_code' ? 'CloudPCS · defect-code statuses' : 'Severity statuses'}
        </span>
      )}
      {route === 'map' && session && (
        <span
          className={`status-badge ${session.synthetic ? 'badge-synthetic' : ''}`}
          data-testid="source-badge"
        >
          {session.synthetic ? 'SYNTHETIC example data' : 'Uploaded inspection files'}
        </span>
      )}
      <button
        type="button"
        className="btn icon-btn"
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        onClick={onToggleTheme}
      >
        {theme === 'dark' ? '☀' : '☾'}
      </button>
    </header>
  )
}
