import { useMemo } from 'react'
import type { Analysis, Reference } from '../api/types'
import { buildIndividualFigure } from '../charts/waferFigures'
import { fmt } from '../format'
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
  const figure = useMemo(
    () => buildIndividualFigure(reference, one.status_codes, analysis.states, analysis.colors, colors, showLabels),
    [reference, one, analysis.states, analysis.colors, colors, showLabels],
  )

  return (
    <section className="card">
      <div className="card-header">
        <div>
          <div className="micro-label">Individual wafer</div>
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
          <div className="legend-inline">
            {analysis.states.map((s) => (
              <span key={s}>
                <i className="swatch swatch-line" style={{ background: analysis.colors[s] }} />
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>
      <PlotlyChart data={figure.data} layout={figure.layout} className="plot-wafer" testId="individual-map" />
      <div className="chart-note">
        Green = Good | Yellow = Low | Orange = Med | Red = Killer | Gray = uninspected. Horizontal spring
        segments span 4 mm in X; visual line thickness is screen-dependent. {analysis.caveats.line_width}
      </div>
      <div className="two-col" style={{ marginTop: 12 }}>
        <div>
          <div className="micro-label">Observed status counts (this wafer)</div>
          <table data-testid="status-counts">
            <thead>
              <tr><th>Status</th><th className="col-num">Count</th></tr>
            </thead>
            <tbody>
              {one.counts.map((c) => (
                <tr key={c.status}>
                  <td>
                    <i className="swatch" style={{ background: analysis.colors[c.status as keyof typeof analysis.colors] ?? 'transparent', marginRight: 6 }} />
                    {c.status}
                  </td>
                  <td className="col-num">{fmt(c.count)}</td>
                </tr>
              ))}
              <tr>
                <td className="cell-muted">Uninspected (reference springs without an observation)</td>
                <td className="col-num cell-muted">{fmt(one.uninspected)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="chart-note">
          {analysis.caveats.uninspected} The counts table lists observed statuses only; the uninspected row is
          derived from the reference and is never folded into Good.
        </div>
      </div>
    </section>
  )
}
