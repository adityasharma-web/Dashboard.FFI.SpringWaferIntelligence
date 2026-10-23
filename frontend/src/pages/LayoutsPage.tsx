import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { LayoutItem, LayoutPreview } from '../api/types'
import { buildLayoutFigure } from '../charts/waferFigures'
import { DataTable, type Column } from '../components/DataTable'
import { PlotlyChart } from '../components/PlotlyChart'
import { fmt } from '../format'
import { navigate } from '../router'
import type { ChartColors } from '../theme/chartColors'

interface Props {
  colors: ChartColors
}

interface GangRow {
  die: number
  springs: number
  xmin: number
  xmax: number
  ymin: number
  ymax: number
}

const GANG_COLUMNS: Column<GangRow>[] = [
  { key: 'die', label: 'Die_Num', numeric: true, render: (r) => r.die },
  { key: 'springs', label: 'Springs', numeric: true, render: (r) => r.springs },
  { key: 'xmin', label: 'x min', numeric: true, render: (r) => fmt(r.xmin, 3) },
  { key: 'xmax', label: 'x max', numeric: true, render: (r) => fmt(r.xmax, 3) },
  { key: 'ymin', label: 'y min', numeric: true, render: (r) => fmt(r.ymin, 3) },
  { key: 'ymax', label: 'y max', numeric: true, render: (r) => fmt(r.ymax, 3) },
]

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function formatSavedAt(value: string | null): string {
  if (!value) return 'pre-existing file'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

export function LayoutsPage({ colors }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [layouts, setLayouts] = useState<LayoutItem[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<LayoutPreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [products, setProducts] = useState('')
  const [replace, setReplace] = useState(false)
  const [showLabels, setShowLabels] = useState(true)
  const [busy, setBusy] = useState<'preview' | 'save' | 'delete' | 'list' | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState<LayoutItem | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const refreshList = useCallback(async () => {
    setBusy('list')
    try {
      setLayouts((await api.layouts()).layouts)
      setListError(null)
    } catch (err) {
      setListError(`Could not load layouts: ${errorText(err)}`)
    } finally {
      setBusy(null)
    }
  }, [])

  useEffect(() => {
    void refreshList()
  }, [refreshList])

  const onFileChange = useCallback(async (picked: File | null) => {
    setFile(picked)
    setPreview(null)
    setPreviewError(null)
    setSaveError(null)
    setSaved(null)
    if (!picked) return
    setBusy('preview')
    try {
      const result = await api.previewLayout(picked)
      setPreview(result)
      setName((current) => current.trim() || result.suggested_name)
      setProducts((current) => current.trim() || result.suggested_name)
    } catch (err) {
      setPreviewError(errorText(err))
    } finally {
      setBusy(null)
    }
  }, [])

  const existingNames = useMemo(() => new Set(layouts.map((l) => l.name.toLowerCase())), [layouts])
  const justSaved = saved !== null && saved.name.toLowerCase() === name.trim().toLowerCase()
  const nameTaken = name.trim() !== '' && existingNames.has(name.trim().toLowerCase()) && !justSaved

  const save = useCallback(async () => {
    if (!file || !preview) return
    setBusy('save')
    setSaveError(null)
    try {
      const item = await api.saveLayout({ name: name.trim(), products, replace, file })
      setSaved(item)
      setReplace(false)
      await refreshList()
    } catch (err) {
      setSaveError(errorText(err))
    } finally {
      setBusy(null)
    }
  }, [file, preview, name, products, replace, refreshList])

  const remove = useCallback(async (layoutName: string) => {
    setBusy('delete')
    try {
      await api.deleteLayout(layoutName)
      setConfirmDelete(null)
      if (saved?.name === layoutName) setSaved(null)
      await refreshList()
    } catch (err) {
      setListError(`Could not delete ${layoutName}: ${errorText(err)}`)
    } finally {
      setBusy(null)
    }
  }, [refreshList, saved])

  const figure = useMemo(() => (preview ? buildLayoutFigure(preview, colors, showLabels) : null), [preview, colors, showLabels])
  const gangRows = useMemo<GangRow[]>(() => {
    if (!preview) return []
    const counts = new Map<number, number>()
    for (const d of preview.die) counts.set(d, (counts.get(d) ?? 0) + 1)
    return preview.gangs.map((g) => ({ die: g.die, springs: counts.get(g.die) ?? 0, xmin: g.xmin, xmax: g.xmax, ymin: g.ymin, ymax: g.ymax }))
  }, [preview])

  const summary = preview?.summary
  const canSave = Boolean(file && preview && name.trim() && busy === null && !justSaved && (!nameTaken || replace))

  return (
    <div className="workbench-grid">
      <aside className="sidebar">
        <section className="card">
          <div className="micro-label">Upload a layout</div>
          <div className="field file-field">
            <label className="field-label" htmlFor="layout-file">Coordinate file (CSV or XLSX)</label>
            <input
              id="layout-file"
              ref={fileInput}
              type="file"
              accept=".csv,.xlsx"
              disabled={busy !== null}
              onChange={(e) => void onFileChange(e.target.files?.[0] ?? null)}
            />
            <div className="file-name">
              Spring layout: Die_Num, Spring_Num, X, Y (one row per spring). Die layout: Die #, X, Y (one row per die).
              mm or µm (auto-detected); header descriptions in parentheses are fine.
            </div>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="layout-name">Layout name</label>
            <input
              id="layout-name"
              className="input"
              type="text"
              value={name}
              placeholder="e.g. 152-900530D"
              disabled={busy !== null}
              onChange={(e) => { setName(e.target.value); setSaveError(null) }}
            />
            {nameTaken && !replace && (
              <div className="file-name" data-testid="name-taken">A layout with this name already exists. Tick Replace to overwrite it.</div>
            )}
          </div>
          <div className="field">
            <label className="field-label" htmlFor="layout-products">Design / product names this layout serves</label>
            <textarea
              id="layout-products"
              className="input textarea"
              rows={3}
              value={products}
              placeholder="One per line or comma-separated, e.g. 152-900530D, 152-900530E"
              disabled={busy !== null}
              onChange={(e) => { setProducts(e.target.value); setSaveError(null) }}
            />
            <div className="file-name">These are the names the wafer map's Product selector and CloudPCS exports use. Designs that share a layout can all point here.</div>
          </div>
          <label className="checkbox-row">
            <input type="checkbox" checked={replace} disabled={busy !== null} onChange={(e) => setReplace(e.target.checked)} />
            Replace existing layout with the same name
          </label>
          <div className="stack" style={{ gap: 8, marginTop: 10 }}>
            <button type="button" className="btn btn-accent btn-full" disabled={!canSave} onClick={() => void save()} data-testid="save-layout">
              {busy === 'save' ? 'Saving…' : 'Save layout'}
            </button>
            <button type="button" className="btn btn-full" disabled={busy !== null} onClick={() => navigate('map')}>
              Back to wafer map
            </button>
          </div>
          <div className="sidebar-status" style={{ marginTop: 10 }}>
            <span className={`status-dot ${busy ? 'dot-warning' : preview ? 'dot-normal' : 'dot-nodata'}`} />
            <span>
              {busy === 'preview' && 'Parsing coordinate file…'}
              {busy === 'save' && 'Saving layout…'}
              {busy === 'delete' && 'Deleting layout…'}
              {busy === 'list' && 'Loading layouts…'}
              {busy === null && (preview ? 'Preview ready. Check the map, then save.' : 'Choose a coordinate file to preview it.')}
            </span>
          </div>
        </section>

        <section className="card">
          <div className="micro-label">Preview options</div>
          <label className="checkbox-row">
            <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
            Show gang outlines and labels
          </label>
          <div className="info-strip">
            The map centers the layout on the bounding-box midpoint of its coordinates and assumes notch down. Validate against physical fiducials before relying on positions.
          </div>
        </section>
      </aside>

      <main className={busy === 'preview' || busy === 'save' ? 'loading-dim' : undefined}>
        <div className="caveat-note">
          <strong>Layouts are the product coordinate references.</strong> A wafer map can only be drawn for a design whose layout is saved here. Upload the coordinate file, check the preview, then save it under a name and the design / product names it applies to.
        </div>

        {saved && (
          <div className="warning-banner" role="status" data-testid="saved-banner" style={{ borderLeftColor: 'var(--good)' }}>
            <div>
              ✓ Saved layout <strong>{saved.name}</strong> ({fmt(saved.summary?.springs ?? 0)} springs, {fmt(saved.summary?.gangs ?? 0)} gangs) for {saved.products.join(', ')}.
              It is now selectable in the wafer map's Product list.{' '}
              <button type="button" className="btn btn-sm" onClick={() => navigate('map')}>Open wafer map</button>
            </div>
          </div>
        )}
        {saveError && <div className="error-banner" role="alert" data-testid="save-error">{saveError}</div>}
        {previewError && <div className="error-banner" role="alert" data-testid="preview-error">Could not read the coordinate file: {previewError}</div>}

        {preview && summary && figure && (
          <section className="card" style={{ marginBottom: 14 }}>
            <div className="card-header">
              <div>
                <div className="micro-label">{justSaved ? `Preview · saved as ${saved?.name}` : 'Preview · not saved yet'}</div>
                <h2 className="card-title">{preview.filename}</h2>
              </div>
              <div className="card-actions">
                <span className="inline-metric" data-testid="preview-kind"><span>Kind</span><strong>{summary.kind === 'die' ? 'Die map' : 'Spring map'}</strong></span>
                {summary.kind === 'die' ? (
                  <>
                    <span className="inline-metric"><span>Dies</span><strong>{fmt(summary.gangs)}</strong></span>
                    <span className="inline-metric">
                      <span>Grid pitch</span>
                      <strong>{summary.pitch_x_mm !== null && summary.pitch_y_mm !== null ? `${fmt(summary.pitch_x_mm, 2)} × ${fmt(summary.pitch_y_mm, 2)} mm` : '—'}</strong>
                    </span>
                  </>
                ) : (
                  <>
                    <span className="inline-metric"><span>Springs</span><strong>{fmt(summary.springs)}</strong></span>
                    <span className="inline-metric"><span>Gangs</span><strong>{fmt(summary.gangs)}</strong></span>
                    <span className="inline-metric">
                      <span>Springs / gang</span>
                      <strong>{summary.springs_per_gang_min === summary.springs_per_gang_max ? fmt(summary.springs_per_gang_min) : `${fmt(summary.springs_per_gang_min)}–${fmt(summary.springs_per_gang_max)}`}</strong>
                    </span>
                  </>
                )}
                <span className="inline-metric"><span>Units</span><strong>{summary.units === 'um->mm' ? 'µm → mm' : 'mm'}</strong></span>
                <span className="inline-metric"><span>Max radius</span><strong className={summary.max_radius_mm > 100 ? 'status-alarm' : undefined}>{fmt(summary.max_radius_mm, 1)} mm</strong></span>
              </div>
            </div>
            {summary.warnings.length > 0 && (
              <div className="warning-banner" role="note" data-testid="preview-warnings">
                {summary.warnings.map((w) => <div key={w}>⚠ {w}</div>)}
              </div>
            )}
            <PlotlyChart data={figure.data} layout={figure.layout} className="plot-wafer" testId="layout-map" />
            <div className="chart-note">
              {preview.caveat} Source extents: X {fmt(summary.x_min, 3)} to {fmt(summary.x_max, 3)} mm, Y {fmt(summary.y_min, 3)} to {fmt(summary.y_max, 3)} mm.
              {summary.kind === 'die'
                ? ' Die layout (no spring level): each die is drawn as a cell at the grid pitch because the file carries no die dimensions; hover shows die and centered position.'
                : ' Springs are drawn as 4 mm horizontal segments; hover shows die, spring and centered position.'}
            </div>
            <details style={{ marginTop: 10 }}>
              <summary className="micro-label" style={{ cursor: 'pointer' }}>{summary.kind === 'die' ? `Die positions (${fmt(gangRows.length)} dies)` : `Gang extents (${fmt(gangRows.length)} gangs)`}</summary>
              <DataTable columns={GANG_COLUMNS} rows={gangRows} rowKey={(r) => String(r.die)} pageSize={200} testId="gang-extents" />
            </details>
          </section>
        )}

        <section className="card">
          <div className="card-header">
            <div>
              <div className="micro-label">Saved layouts</div>
              <h2 className="card-title">{fmt(layouts.length)} layout{layouts.length === 1 ? '' : 's'} available to the wafer map</h2>
            </div>
            <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => void refreshList()}>Refresh</button>
          </div>
          {listError && <div className="error-banner" role="alert">{listError}</div>}
          <div className="table-scroll table-scroll-tall">
            <table data-testid="layouts-table">
              <thead>
                <tr>
                  <th>Layout</th>
                  <th>Kind</th>
                  <th>Design / product names</th>
                  <th className="col-num">Springs</th>
                  <th className="col-num">Gangs</th>
                  <th className="col-num">Springs / gang</th>
                  <th>Center (mm)</th>
                  <th>File</th>
                  <th>Saved</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {layouts.length === 0 && !listError && (
                  <tr><td colSpan={10} className="cell-muted">No layouts yet. Upload a coordinate file to create the first one.</td></tr>
                )}
                {layouts.map((l) => (
                  <tr key={l.name}>
                    <td><strong>{l.name}</strong>{l.implicit && <span className="cell-muted"> (file only)</span>}</td>
                    <td>{l.summary ? (l.summary.kind === 'die' ? 'Die map' : 'Spring map') : '—'}</td>
                    <td>{l.products.join(', ')}</td>
                    <td className="col-num">{l.summary ? fmt(l.summary.springs) : '—'}</td>
                    <td className="col-num">{l.summary ? fmt(l.summary.gangs) : '—'}</td>
                    <td className="col-num">
                      {l.summary
                        ? l.summary.springs_per_gang_min === l.summary.springs_per_gang_max
                          ? fmt(l.summary.springs_per_gang_min)
                          : `${fmt(l.summary.springs_per_gang_min)}–${fmt(l.summary.springs_per_gang_max)}`
                        : '—'}
                    </td>
                    <td className="num">{l.summary ? `${fmt(l.summary.center_x, 3)}, ${fmt(l.summary.center_y, 3)}` : '—'}</td>
                    <td className="cell-muted" title={l.source_filename ?? undefined}>{l.file}{l.error && <span className="status-alarm"> · {l.error}</span>}</td>
                    <td className="cell-muted">{formatSavedAt(l.saved_at)}</td>
                    <td>
                      {confirmDelete === l.name ? (
                        <span className="card-actions">
                          <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => void remove(l.name)} data-testid={`confirm-delete-${l.name}`}>Confirm delete</button>
                          <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => setConfirmDelete(null)}>Cancel</button>
                        </span>
                      ) : (
                        <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => setConfirmDelete(l.name)} data-testid={`delete-${l.name}`}>Delete</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="chart-note">
            Deleting a layout removes its coordinate file; wafer maps for its design names stop working until a layout is uploaded again.
          </div>
        </section>
      </main>
    </div>
  )
}
