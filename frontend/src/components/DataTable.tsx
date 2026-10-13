import { useState, type ReactNode } from 'react'
import { fmt } from '../format'

export interface Column<T> {
  key: string
  label: string
  numeric?: boolean
  render: (row: T) => ReactNode
  className?: (row: T) => string | undefined
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  pageSize?: number
  tall?: boolean
  emptyMessage?: string
  testId?: string
}

/* Scrollable table with incremental "show more" so the 21k-row stacked table
   and the 648-row gang table stay responsive without a grid library. */
export function DataTable<T>({ columns, rows, rowKey, pageSize = 300, tall, emptyMessage = 'No rows.', testId }: Props<T>) {
  const [limit, setLimit] = useState(pageSize)
  const visible = rows.slice(0, limit)

  return (
    <div>
      <div className={`table-scroll ${tall ? 'table-scroll-tall' : ''}`}>
        <table data-testid={testId}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={c.numeric ? 'col-num' : undefined}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="cell-muted">{emptyMessage}</td>
              </tr>
            )}
            {visible.map((row) => (
              <tr key={rowKey(row)}>
                {columns.map((c) => (
                  <td key={c.key} className={[c.numeric ? 'col-num' : '', c.className?.(row) ?? ''].join(' ').trim() || undefined}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-foot">
        <span>
          Showing {fmt(visible.length)} of {fmt(rows.length)} rows
        </span>
        {rows.length > visible.length && (
          <span>
            <button type="button" className="btn btn-sm" onClick={() => setLimit((l) => l + pageSize)}>
              Show {fmt(Math.min(pageSize, rows.length - visible.length))} more
            </button>{' '}
            <button type="button" className="btn btn-sm" onClick={() => setLimit(rows.length)}>
              Show all
            </button>
          </span>
        )}
      </div>
    </div>
  )
}
