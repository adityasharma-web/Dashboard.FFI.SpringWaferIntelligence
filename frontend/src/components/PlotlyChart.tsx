import Plotly from 'plotly.js-dist-min'
import { useEffect, useRef } from 'react'

/* plotly.js is bundled locally at build time; charts stay fully offline. */

const PLOT_CONFIG = {
  responsive: true,
  displaylogo: false,
  scrollZoom: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
}

interface Props {
  data: Record<string, unknown>[]
  layout: Record<string, unknown>
  className?: string
  testId?: string
}

export function PlotlyChart({ data, layout, className, testId }: Props) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = container.current
    if (!node) return
    void Plotly.react(node, data as Plotly.Data[], layout, PLOT_CONFIG as Partial<Plotly.Config>)
  }, [data, layout])

  useEffect(() => {
    const node = container.current
    return () => {
      if (node) Plotly.purge(node)
    }
  }, [])

  return <div ref={container} className={className} data-testid={testId} />
}
