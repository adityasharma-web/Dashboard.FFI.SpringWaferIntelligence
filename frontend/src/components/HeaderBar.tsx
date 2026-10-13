import type { InspectionsResponse } from '../api/types'
import type { Theme } from '../theme/useTheme'

interface Props {
  product: string | null
  session: InspectionsResponse | null
  theme: Theme
  onToggleTheme: () => void
}

export function HeaderBar({ product, session, theme, onToggleTheme }: Props) {
  return (
    <header className="top-header">
      <div>
        <h1 className="app-title">Spring Wafer Intelligence</h1>
        <div className="app-subtitle">
          Product-based coordinate registration · Individual inspection · Multi-wafer spatial signatures
        </div>
      </div>
      <div className="header-spacer" />
      {product && (
        <span className="dataset-pill" title={`Product ${product}`}>
          {product}
          {session ? ` · ${session.wafers.length} wafer${session.wafers.length === 1 ? '' : 's'}` : ''}
        </span>
      )}
      <span className="status-badge">Notch ↓ (assumed)</span>
      {session && (
        <span className="status-badge" data-testid="status-model-badge">
          {session.status_model === 'defect_code' ? 'CloudPCS · defect-code statuses' : 'Severity statuses'}
        </span>
      )}
      {session && (
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
