import { useMemo } from 'react'
import type { Analysis, Peak, RecurrenceRow, Reference, SectorRow, ZoneRow } from '../api/types'
import { buildHeatmapFigure } from '../charts/waferFigures'
import { fmt, pct, sci } from '../format'
import type { ChartColors } from '../theme/chartColors'
import { DataTable, type Column } from './DataTable'
import { PlotlyChart } from './PlotlyChart'

interface Props {
  analysis: Analysis
  reference: Reference
  colors: ChartColors
}

const ZONE_COLUMNS: Column<ZoneRow>[] = [
  { key: 'zone', label: 'Zone (mm radius)', render: (r) => r.zone },
  { key: 'inspected', label: 'Inspected', numeric: true, render: (r) => fmt(r.inspected) },
  { key: 'defects', label: 'Defects', numeric: true, render: (r) => fmt(r.defects) },
  { key: 'rate', label: 'Defect_Rate', numeric: true, render: (r) => pct(r.defect_rate, 2) },
]

const SECTOR_COLUMNS: Column<SectorRow>[] = [
  { key: 'sector', label: 'Outer sector (rad)', render: (r) => r.sector },
  { key: 'size', label: 'Observations', numeric: true, render: (r) => fmt(r.size) },
  { key: 'rate', label: 'Defect rate', numeric: true, render: (r) => pct(r.defect_rate, 2, '—') },
]

const PEAK_COLUMNS: Column<Peak>[] = [
  { key: 'x', label: 'X_mm', numeric: true, render: (r) => fmt(r.X_mm, 1) },
  { key: 'y', label: 'Y_mm', numeric: true, render: (r) => fmt(r.Y_mm, 1) },
  { key: 'rate', label: 'Local_defect_rate', numeric: true, render: (r) => fmt(r.Local_defect_rate, 3) },
  { key: 'excess', label: 'Excess_vs_global', numeric: true, render: (r) => fmt(r.Excess_vs_global, 3) },
]

const RECURRENCE_COLUMNS: Column<RecurrenceRow>[] = [
  { key: 'die', label: 'Die_Num', numeric: true, render: (r) => r.die },
  { key: 'spring', label: 'Spring_Num', numeric: true, render: (r) => r.spring },
  { key: 'inspected', label: 'Inspected', numeric: true, render: (r) => r.inspected },
  { key: 'defects', label: 'Defects', numeric: true, render: (r) => r.defects },
  { key: 'q', label: 'q', numeric: true, render: (r) => sci(r.q) },
  { key: 'p', label: 'p', numeric: true, render: (r) => sci(r.p) },
]

export function SpatialPanel({ analysis, reference, colors }: Props) {
  const figure = useMemo(() => buildHeatmapFigure(analysis, reference, colors), [analysis, reference, colors])
  const s = analysis.spatial

  return (
    <div className="stack">
      <section className="card">
        <div className="card-header">
          <div>
            <div className="micro-label">Spatial signatures</div>
            <h2 className="card-title">
              Smoothed stacked defect incidence · {fmt(analysis.bandwidth)} mm bandwidth
              {analysis.synthetic ? ' · synthetic' : ''}
            </h2>
          </div>
          <span className="inline-metric"><span>Global baseline</span><strong>{pct(s.baseline, 1)}</strong></span>
        </div>
        <PlotlyChart data={figure.data} layout={figure.layout} className="plot-wafer" testId="heatmap" />
        <div className="chart-note">{analysis.caveats.heatmap}</div>
      </section>

      <div className="two-col">
        <section className="card">
          <div className="micro-label">Signature indicators</div>
          <ul className="bullet-list" data-testid="indicator-messages">
            {analysis.signature.messages.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
          <div className="chart-note" style={{ marginBottom: 8 }}>{analysis.caveats.signatures}</div>
          <table data-testid="zones-table">
            <thead>
              <tr>{ZONE_COLUMNS.map((c) => <th key={c.key} className={c.numeric ? 'col-num' : undefined}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {analysis.signature.zones.map((z) => (
                <tr key={z.zone}>{ZONE_COLUMNS.map((c) => <td key={c.key} className={c.numeric ? 'col-num' : undefined}>{c.render(z)}</td>)}</tr>
              ))}
            </tbody>
          </table>
          <details style={{ marginTop: 10 }}>
            <summary className="micro-label" style={{ cursor: 'pointer' }}>Outer-region angular sectors (what the angular heuristic evaluated)</summary>
            <table>
              <thead>
                <tr>{SECTOR_COLUMNS.map((c) => <th key={c.key} className={c.numeric ? 'col-num' : undefined}>{c.label}</th>)}</tr>
              </thead>
              <tbody>
                {analysis.signature.sectors.map((r) => (
                  <tr key={r.sector}>{SECTOR_COLUMNS.map((c) => <td key={c.key} className={c.numeric ? 'col-num' : undefined}>{c.render(r)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>

        <section className="card">
          <div className="micro-label">Candidate recurring hotspots</div>
          <div className="chart-note" style={{ marginBottom: 8 }}>
            Local maxima of smoothed excess over the global baseline (excess &gt; 0.08, exposure ≥ max(4, 2 × wafers),
            top 8). Peak candidates are spatial excess maxima, not confirmed root causes.
          </div>
          <DataTable
            columns={PEAK_COLUMNS}
            rows={s.peaks}
            rowKey={(r) => `${r.X_mm}-${r.Y_mm}`}
            emptyMessage="No peaks exceed current excess threshold"
            testId="hotspots-table"
          />
        </section>
      </div>

      <section className="card">
        <div className="card-header">
          <div className="micro-label">Spring-level recurrence</div>
          <span className="inline-metric">
            <span>Tested springs</span>
            <strong>{fmt(s.recurrence_total_rows)}</strong>
            <span>· inspected ≥ {s.recurrence_min_inspected}</span>
          </span>
        </div>
        <div className="chart-note" style={{ marginBottom: 8 }}>
          Global baseline = {pct(s.baseline, 1)}. {analysis.caveats.recurrence}
          {!s.recurrence_tested && ' No binomial test was possible for this selection (baseline is 0 or 1); q is reported as 1.0.'}
          {' '}Showing the top 100 by q, then by defect count.
        </div>
        <DataTable columns={RECURRENCE_COLUMNS} rows={s.recurrence} rowKey={(r) => `${r.die}-${r.spring}`} testId="recurrence-table" />
      </section>
    </div>
  )
}
