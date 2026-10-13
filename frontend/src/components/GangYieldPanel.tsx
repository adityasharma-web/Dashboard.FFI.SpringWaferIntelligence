import { useMemo, useState } from 'react'
import type { Analysis, GangRow } from '../api/types'
import { fmt, pct } from '../format'
import { DataTable, type Column } from './DataTable'

interface Props {
  analysis: Analysis
}

const COLUMNS: Column<GangRow>[] = [
  { key: 'wafer', label: 'Wafer_ID', render: (r) => r.wafer_id },
  { key: 'die', label: 'Die_Num', numeric: true, render: (r) => r.die },
  { key: 'inspected', label: 'Inspected', numeric: true, render: (r) => r.inspected },
  { key: 'bad', label: 'Bad', numeric: true, render: (r) => r.bad },
  { key: 'total', label: 'Total_Springs', numeric: true, render: (r) => r.total_springs },
  { key: 'pct', label: 'Bad_Pct', numeric: true, render: (r) => pct(r.bad_pct, 2) },
  { key: 'complete', label: 'Complete_Inspection', render: (r) => (r.complete ? 'True' : 'False'), className: (r) => (r.complete ? undefined : 'disp-INCOMPLETE') },
  { key: 'disp', label: 'Disposition', render: (r) => r.disposition, className: (r) => `disp-${r.disposition}` },
]

export function GangYieldPanel({ analysis }: Props) {
  const [filter, setFilter] = useState<'all' | 'SCRAP' | 'INCOMPLETE' | 'PASS'>('all')
  const g = analysis.gang_yield
  const rows = useMemo(() => (filter === 'all' ? g.rows : g.rows.filter((r) => r.disposition === filter)), [g.rows, filter])
  const incomplete = g.rows.filter((r) => r.disposition === 'INCOMPLETE').length

  return (
    <section className="card">
      <div className="card-header">
        <div>
          <div className="micro-label">Gang yield</div>
          <h2 className="card-title">Per-wafer per-gang disposition{analysis.synthetic ? ' · synthetic' : ''}</h2>
        </div>
        <div className="card-actions">
          <span className="inline-metric" data-testid="scrapped-metric">
            <span>Scrapped wafer-gangs</span>
            <strong className={g.scrapped > 0 ? 'status-alarm' : undefined}>{fmt(g.scrapped)}</strong>
            <span>of {fmt(g.total)}</span>
          </span>
          <span className="inline-metric">
            <span>Incomplete</span>
            <strong className={incomplete > 0 ? 'status-warning' : undefined}>{fmt(incomplete)}</strong>
          </span>
          <label className="field-label" htmlFor="gang-filter" style={{ marginBottom: 0 }}>Show</label>
          <select id="gang-filter" className="select select-sm" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
            <option value="all">All dispositions</option>
            <option value="SCRAP">SCRAP only</option>
            <option value="INCOMPLETE">INCOMPLETE only</option>
            <option value="PASS">PASS only</option>
          </select>
        </div>
      </div>
      <div className="chart-note" style={{ marginBottom: 8 }} data-testid="gang-rule">
        <strong>Rule:</strong> {g.rule} Bad fraction uses the total reference spring count of the gang
        ({fmt(g.threshold * 100)}% exactly is not scrap; strictly greater is).
      </div>
      <DataTable columns={COLUMNS} rows={rows} rowKey={(r) => `${r.wafer_id}-${r.die}`} tall testId="gang-table" />
    </section>
  )
}
