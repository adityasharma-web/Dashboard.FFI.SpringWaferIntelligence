import { exportUrl } from '../api/client'
import type { Analysis } from '../api/types'
import { fmt } from '../format'

interface Props {
  analysis: Analysis
}

export function ExportPanel({ analysis }: Props) {
  const stacked = exportUrl('stacked', analysis.session_id, analysis.wafers)
  const inspection = exportUrl('inspection', analysis.session_id, analysis.wafers)

  return (
    <section className="card">
      <div className="micro-label">Export</div>
      <div className="two-col">
        <div className="card">
          <h2 className="card-title">Stacked spring metrics</h2>
          <div className="chart-note" style={{ marginBottom: 10 }}>
            One row per reference spring ({fmt(analysis.header.springs_in_reference)} rows) with centered x / y,
            Inspected, Defects, Killer and Defect_Rate across the {fmt(analysis.wafers.length)} selected
            wafer{analysis.wafers.length === 1 ? '' : 's'}. Uninspected springs have an empty Defect_Rate.
          </div>
          <a className="btn btn-accent" href={stacked} download data-testid="export-stacked">
            Download stacked spring metrics (CSV)
          </a>
        </div>
        <div className="card">
          <h2 className="card-title">Normalized inspection data</h2>
          <div className="chart-note" style={{ marginBottom: 10 }}>
            Wafer_ID, Die_Num, Spring_Num, Status for every observation of the selected wafers
            ({fmt(analysis.header.observations)} rows).
          </div>
          <a className="btn btn-accent" href={inspection} download data-testid="export-inspection">
            Download normalized inspection data (CSV)
          </a>
        </div>
      </div>
      <div className="chart-note" style={{ marginTop: 10 }}>
        {analysis.caveats.export}
        {analysis.synthetic && ` ${analysis.caveats.synthetic}`}
      </div>
    </section>
  )
}
