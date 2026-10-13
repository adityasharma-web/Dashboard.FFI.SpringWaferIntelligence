import { useRef, useState, type CSSProperties } from 'react'
import type { InspectionsResponse, Reference } from '../api/types'
import { fmt } from '../format'

export const BANDWIDTH_MIN = 2
export const BANDWIDTH_MAX = 15

interface Props {
  products: string[]
  product: string | null
  onProductChange: (product: string) => void
  reference: Reference | null
  session: InspectionsResponse | null
  selectedWafers: string[]
  onSelectedWafersChange: (wafers: string[]) => void
  showLabels: boolean
  onShowLabelsChange: (value: boolean) => void
  bandwidth: number
  onBandwidthChange: (value: number) => void
  examplesAvailable: boolean
  onLoadExamples: () => void
  onUpload: (files: File[]) => void
  loading: boolean
  status: string
}

export function ControlsPanel({
  products,
  product,
  onProductChange,
  reference,
  session,
  selectedWafers,
  onSelectedWafersChange,
  showLabels,
  onShowLabelsChange,
  bandwidth,
  onBandwidthChange,
  examplesAvailable,
  onLoadExamples,
  onUpload,
  loading,
  status,
}: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [pendingFiles, setPendingFiles] = useState<string[]>([])
  const fillPct = `${((bandwidth - BANDWIDTH_MIN) / (BANDWIDTH_MAX - BANDWIDTH_MIN)) * 100}%`

  const toggleWafer = (wafer: string) => {
    const set = new Set(selectedWafers)
    if (set.has(wafer)) set.delete(wafer)
    else set.add(wafer)
    onSelectedWafersChange((session?.wafers ?? []).filter((w) => set.has(w)))
  }

  return (
    <aside className="sidebar">
      <section className="card">
        <div className="micro-label">1 · Product &amp; inputs</div>
        <div className="field">
          <label className="field-label" htmlFor="product-select">Product</label>
          <select
            id="product-select"
            className="select"
            value={product ?? ''}
            disabled={loading || products.length === 0}
            onChange={(e) => onProductChange(e.target.value)}
          >
            {products.length === 0 && <option value="">No coordinate reference found</option>}
            {products.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <div className="field file-field">
          <label className="field-label" htmlFor="inspection-files">
            Inspection files (CSV / XLSX / CloudPCS XML; one wafer per file)
          </label>
          <input
            id="inspection-files"
            ref={fileInput}
            type="file"
            multiple
            accept=".csv,.xlsx,.xml"
            onChange={(e) => setPendingFiles(Array.from(e.target.files ?? []).map((f) => f.name))}
          />
          {pendingFiles.length > 0 && (
            <div className="file-name" title={pendingFiles.join(', ')}>
              {pendingFiles.length} file{pendingFiles.length === 1 ? '' : 's'} selected
            </div>
          )}
        </div>
        <div className="stack" style={{ gap: 8 }}>
          <button
            type="button"
            className="btn btn-accent btn-full"
            disabled={loading || !product}
            onClick={() => onUpload(Array.from(fileInput.current?.files ?? []))}
          >
            Analyze uploads
          </button>
          <button
            type="button"
            className="btn btn-full"
            disabled={loading || !examplesAvailable}
            title="Bundled example wafers are explicitly simulated data"
            onClick={onLoadExamples}
          >
            Load synthetic examples
          </button>
        </div>
        {reference && (
          <div className="info-strip" data-testid="center-caveat">
            Coordinate center inferred from extents: X={fmt(reference.center.x, 3)}, Y={fmt(reference.center.y, 3)} mm.
            Notch down assumed. {fmt(reference.spring_count)} springs in {fmt(reference.gang_count)} gangs.
          </div>
        )}
      </section>

      <section className="card">
        <div className="micro-label">2 · Wafers to analyze</div>
        {!session && <div className="file-name">Upload inspection files or load the synthetic examples.</div>}
        {session && (
          <>
            <div className="list-actions">
              <span>{selectedWafers.length} of {session.wafers.length} selected</span>
              <div>
                <button type="button" onClick={() => onSelectedWafersChange([...session.wafers])}>All</button>
                <button type="button" onClick={() => onSelectedWafersChange([])}>None</button>
              </div>
            </div>
            <div className="checkbox-list" role="group" aria-label="Wafers to analyze">
              {session.wafers.map((w) => (
                <label key={w} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={selectedWafers.includes(w)}
                    disabled={loading}
                    onChange={() => toggleWafer(w)}
                  />
                  {w}
                </label>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="card">
        <div className="micro-label">3 · Display &amp; smoothing</div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={showLabels}
            onChange={(e) => onShowLabelsChange(e.target.checked)}
          />
          Show gang outlines and labels
        </label>
        <div className="field" style={{ marginTop: 8 }}>
          <div className="slider-head">
            <label className="field-label" htmlFor="bandwidth">Spatial smoothing bandwidth</label>
            <span className="value-readout">{fmt(bandwidth)} mm</span>
          </div>
          <div className="slider-row">
            <input
              id="bandwidth"
              type="range"
              min={BANDWIDTH_MIN}
              max={BANDWIDTH_MAX}
              step={1}
              value={bandwidth}
              style={{ '--fill': fillPct } as CSSProperties}
              onChange={(e) => onBandwidthChange(Number(e.target.value))}
            />
          </div>
        </div>
        <div className="sidebar-status">
          <span className={`status-dot ${loading ? 'dot-warning' : 'dot-normal'}`} />
          <span>{status}</span>
        </div>
      </section>
    </aside>
  )
}
