import type { Analysis } from '../api/types'
import { fmt, pct } from '../format'

interface Props {
  analysis: Analysis
}

/* The four header metrics of the reference app: Wafers, Springs in reference,
   Inspected observations, Defect rate (N/A when nothing was inspected). */
export function KpiCards({ analysis }: Props) {
  const h = analysis.header
  const cards = [
    { label: 'Wafers', value: fmt(h.wafers), sub: analysis.synthetic ? 'synthetic example wafers' : 'selected for analysis' },
    { label: 'Springs in reference', value: fmt(h.springs_in_reference), sub: `${analysis.product} coordinate reference` },
    { label: 'Inspected observations', value: fmt(h.observations), sub: `${fmt(analysis.stacked.uninspected_springs)} reference springs never inspected` },
    {
      label: 'Defect rate',
      value: pct(h.defect_rate, 1),
      sub: `${fmt(h.bad)} defective observations`,
      className: h.defect_rate === null ? 'status-nodata' : undefined,
    },
  ]

  return (
    <section className="kpi-row" aria-label="Header metrics">
      {cards.map((c) => (
        <div key={c.label} className="card">
          <div className="micro-label">{c.label}</div>
          <div className={`kpi-value ${c.className ?? ''}`}>{c.value}</div>
          <div className="kpi-sub" title={c.sub}>{c.sub}</div>
        </div>
      ))}
    </section>
  )
}
