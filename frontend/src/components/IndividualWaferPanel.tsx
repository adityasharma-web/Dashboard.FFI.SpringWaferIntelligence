import { useMemo } from 'react'
import type { Analysis, Reference } from '../api/types'
import { buildIndividualFigure } from '../charts/waferFigures'
import { fmt, pct } from '../format'
import type { ChartColors } from '../theme/chartColors'
import { PlotlyChart } from './PlotlyChart'

interface Props {
  analysis: Analysis
  reference: Reference
  wafer: string
  onWaferChange: (wafer: string) => void
  showLabels: boolean
  colors: ChartColors
}

export function IndividualWaferPanel({ analysis, reference, wafer, onWaferChange, showLabels, colors }: Props) {
  const one = analysis.individual.find((w) => w.wafer_id === wafer) ?? analysis.individual[0]
  const byCode = analysis.status_model === 'defect_code'
  const figure = useMemo(
    () => buildIndividualFigure(reference, one.status_codes, analysis.states, analysis.colors, colors, showLabels),
    [reference, one, analysis.states, analysis.colors, colors, showLabels],
  )
  const observed = one.counts.reduce((sum, c) => sum + c.count, 0)
  const defective = one.counts.filter((c) => c.status !== 'Good').reduce((sum, c) => sum + c.count, 0)

  return (
    <section className="card">
      <div className="card-header">
        <div>
          <div className="micro-label">Individual wafer{byCode ? ' · colored by defect code' : ' · colored by severity'}</div>
          <h2 className="card-title">
            {analysis.product} · {one.wafer_id}
            {analysis.synthetic ? ' · synthetic' : ''}
          </h2>
        </div>
        <div className="card-actions">
          <label className="field-label" htmlFor="wafer-select" style={{ marginBottom: 0 }}>Wafer ID</label>
          <select
            id="wafer-select"
            className="select select-sm"
            value={one.wafer_id}
            onChange={(e) => onWaferChange(e.target.value)}
          >
            {analysis.wafers.map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
          </select>
          {!byCode && (
            <div className="legend-inline">
              {analysis.states.map((s) => (
                <span key={s}>
                  <i className="swatch swatch-line" style={{ background: analysis.colors[s] }} />
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <PlotlyChart data={figure.data} layout={figure.layout} className="plot-wafer" testId="individual-map" />
      <div className="chart-note" data-testid="individual-caption">
        {byCode
          ? 'Green = Good (grading other than SCRAP) | each other color = the DEFECT_CODE of a SCRAP spring | Gray = uninspected. The export carries no severity. '
          : 'Green = Good | Yellow = Low | Orange = Med | Red = Killer | Gray = uninspected. '}
        Horizontal spring segments span 4 mm in X; visual line thickness is screen-dependent. {analysis.caveats.line_width}
        {' '}Click a legend entry to show only that {byCode ? 'defect code' : 'status'}; click it again to restore all.
      </div>
      <div className="two-col" style={{ marginTop: 12 }}>
        <div>
          <div className="micro-label">
            {byCode ? 'Observed springs by defect code (this wafer)' : 'Observed status counts (this wafer)'}
          </div>
          <table data-testid="status-counts">
            <thead>
              <tr><th>{byCode ? 'Status / defect code' : 'Status'}</th><th className="col-num">Count</th><th className="col-num">Share</th></tr>
            </thead>
            <tbody>
              {one.counts.map((c) => (
                <tr key={c.status}>
                  <td>
                    <i className="swatch" style={{ background: analysis.colors[c.status] ?? 'transparent', marginRight: 6 }} />
                    {c.status}
                    {byCode && c.status !== 'Good' && <span className="cell-muted"> (SCRAP)</span>}
                  </td>
                  <td className="col-num">{fmt(c.count)}</td>
                  <td className="col-num cell-muted">{observed ? pct(c.count / observed, 1) : '—'}</td>
                </tr>
              ))}
              <tr>
                <td className="cell-muted">Uninspected (reference springs without an observation)</td>
                <td className="col-num cell-muted">{fmt(one.uninspected)}</td>
                <td className="col-num cell-muted">—</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <div className="stack" style={{ gap: 8, marginBottom: 10 }}>
            <span className="inline-metric"><span>Defective springs</span><strong>{fmt(defective)}</strong><span>{observed ? pct(defective / observed, 1) : '—'} of observed</span></span>
            <span className="inline-metric"><span>Good spring yield</span><strong>{observed ? pct(1 - defective / observed, 1) : '—'}</strong></span>
          </div>
          <div className="chart-note">
            {analysis.caveats.uninspected} The counts table lists observed statuses only; the uninspected row is
            derived from the reference and is never folded into Good.
            {byCode && ' Defect-code colors are provisional and assigned by frequency; code meanings have not been supplied.'}
          </div>
        </div>
      </div>
    </section>
  )
}
