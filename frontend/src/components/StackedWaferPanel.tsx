import { useMemo, useState } from 'react'
import type { Analysis, Reference } from '../api/types'
import { buildStackedFigure } from '../charts/waferFigures'
import { fmt, pct } from '../format'
import type { ChartColors } from '../theme/chartColors'
import { DataTable, type Column } from './DataTable'
import { PlotlyChart } from './PlotlyChart'

interface Props {
  analysis: Analysis
  reference: Reference
  showLabels: boolean
  colors: ChartColors
}

interface StackRow {
  die: number
  spring: number
  inspected: number
  defects: number
  killer: number
  rate: number | null
}

const COLUMNS: Column<StackRow>[] = [
  { key: 'die', label: 'Die_Num', numeric: true, render: (r) => r.die },
  { key: 'spring', label: 'Spring_Num', numeric: true, render: (r) => r.spring },
  { key: 'inspected', label: 'Inspected', numeric: true, render: (r) => r.inspected },
  { key: 'defects', label: 'Defects', numeric: true, render: (r) => r.defects },
  { key: 'killer', label: 'Killer', numeric: true, render: (r) => r.killer },
  {
    key: 'rate',
    label: 'Defect_Rate',
    numeric: true,
    render: (r) => (r.rate === null ? 'uninspected' : pct(r.rate, 1)),
    className: (r) => (r.rate === null ? 'cell-muted' : undefined),
  },
]

export function StackedWaferPanel({ analysis, reference, showLabels, colors }: Props) {
  const [filter, setFilter] = useState<'all' | 'uninspected' | 'defective'>('all')
  // Killer counts only exist in the severity model; CloudPCS exports carry no severity.
  const columns = useMemo(
    () => (analysis.status_model === 'defect_code' ? COLUMNS.filter((c) => c.key !== 'killer') : COLUMNS),
    [analysis.status_model],
  )
  const figure = useMemo(
    () => buildStackedFigure(reference, analysis.stacked.defect_rate, colors, showLabels),
    [reference, analysis.stacked.defect_rate, colors, showLabels],
  )
  const rows = useMemo<StackRow[]>(() => {
    const s = analysis.stacked
    const all = s.die.map((die, i) => ({
      die, spring: s.spring[i], inspected: s.inspected[i], defects: s.defects[i], killer: s.killer[i], rate: s.defect_rate[i],
    }))
    if (filter === 'uninspected') return all.filter((r) => r.inspected === 0)
    if (filter === 'defective') return all.filter((r) => r.defects > 0)
    return all
  }, [analysis.stacked, filter])

  return (
    <section className="card">
      <div className="card-header">
        <div>
          <div className="micro-label">Stacked wafer</div>
          <h2 className="card-title">
            {analysis.product} · {analysis.wafers.length} wafer stack · defect incidence
            {analysis.synthetic ? ' · synthetic' : ''}
          </h2>
        </div>
        <div className="legend-inline">
          <span className="inline-metric"><span>Never inspected</span><strong>{fmt(analysis.stacked.uninspected_springs)}</strong></span>
        </div>
      </div>
      <PlotlyChart data={figure.data} layout={figure.layout} className="plot-wafer" testId="stacked-map" />
      <div className="chart-note">
        Color indicates observed defects / inspected observations per spring. Springs never inspected are
        displayed at zero for map rendering only; use the table below to distinguish missing coverage.
      </div>
      <div className="card-header" style={{ marginTop: 12 }}>
        <div className="micro-label">Per-spring stacked metrics</div>
        <div className="card-actions">
          <label className="field-label" htmlFor="stack-filter" style={{ marginBottom: 0 }}>Rows</label>
          <select id="stack-filter" className="select select-sm" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
            <option value="all">All springs</option>
            <option value="defective">With defects</option>
            <option value="uninspected">Uninspected only</option>
          </select>
        </div>
      </div>
      <DataTable columns={columns} rows={rows} rowKey={(r) => `${r.die}-${r.spring}`} testId="stacked-table" />
      <div className="card-header" style={{ marginTop: 14 }}>
        <div className="micro-label">
          {analysis.status_model === 'defect_code' ? 'Observations by defect code' : 'Observations by status'} · {analysis.wafers.length} selected wafer{analysis.wafers.length === 1 ? '' : 's'}
        </div>
      </div>
      <table data-testid="status-breakdown">
        <thead>
          <tr><th>{analysis.status_model === 'defect_code' ? 'Status / defect code' : 'Status'}</th><th className="col-num">Observations</th><th className="col-num">Share</th></tr>
        </thead>
        <tbody>
          {analysis.status_counts.map((c) => (
            <tr key={c.status}>
              <td><i className="swatch" style={{ background: analysis.colors[c.status] ?? 'transparent', marginRight: 6 }} />{c.status}</td>
              <td className="col-num">{fmt(c.count)}</td>
              <td className="col-num cell-muted">{analysis.header.observations ? pct(c.count / analysis.header.observations, 1) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
