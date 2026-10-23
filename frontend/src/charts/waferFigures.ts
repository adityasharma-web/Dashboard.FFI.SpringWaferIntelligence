/* Faithful ports of decorate() / springs_plot() / the spatial Heatmap from the
   reference app.py. Pure figure builders: no analysis logic, only rendering
   of the API payload. Geometry constants are the reference app's:

   - wafer outline: 100 mm radius (200 mm wafer), 361-point circle
   - notch marker at the bottom: (-3, -99.955) (0, -97.2) (3, -99.955)
   - every spring: a horizontal 4 mm segment (x-2 .. x+2) at its real y
   - gang outline rectangles padded 2 mm in X and 0.2 mm in Y, label 1.3 mm above
   - axes: x in [-106, 106], y in [-108, 106], aspect locked 1:1

   Theme-dependent chrome (wafer edge, background, gang outlines) comes from
   the design tokens; the five spring STATUS colors come from the API. */

import type { Analysis, Reference } from '../api/types'
import { rgba, type ChartColors } from '../theme/chartColors'

export interface Figure {
  data: Record<string, unknown>[]
  layout: Record<string, unknown>
}

export const WAFER_RADIUS_MM = 100
export const SEGMENT_HALF_WIDTH_MM = 2
export const NOTCH = { x: [-3, 0, 3], y: [-99.955, -97.2, -99.955] }
export const AXIS_RANGE = { x: [-106, 106], y: [-108, 106] }

function circlePoints(radius: number): { x: number[]; y: number[] } {
  const x: number[] = []
  const y: number[] = []
  for (let i = 0; i <= 360; i++) {
    const theta = (i / 360) * 2 * Math.PI
    x.push(radius * Math.cos(theta))
    y.push(radius * Math.sin(theta))
  }
  return { x, y }
}

/* decorate(): wafer outline + notch traces, gang outline shapes + die labels,
   and the aspect-locked layout. */
export function decorate(
  data: Record<string, unknown>[],
  reference: Reference,
  colors: ChartColors,
  dieLabels: boolean,
  extraLayout: Record<string, unknown> = {},
): Figure {
  const circle = circlePoints(WAFER_RADIUS_MM)
  const chrome: Record<string, unknown>[] = [
    // Outline only (as in the reference): a filled disc would sit above the
    // WebGL spring segments and the heatmap, which Plotly draws in lower layers.
    {
      type: 'scatter', mode: 'lines', x: circle.x, y: circle.y,
      line: { color: colors.waferEdge, width: 2 },
      hoverinfo: 'skip', showlegend: false, name: 'Wafer',
    },
    {
      type: 'scatter', mode: 'lines', x: NOTCH.x, y: NOTCH.y,
      fill: 'toself', fillcolor: colors.bg,
      line: { color: colors.waferEdge, width: 1.5 },
      hoverinfo: 'skip', showlegend: false, name: 'Notch',
    },
  ]

  const shapes: Record<string, unknown>[] = []
  const annotations: Record<string, unknown>[] = []
  if (dieLabels) {
    for (const g of reference.gangs) {
      shapes.push({
        type: 'rect', xref: 'x', yref: 'y',
        x0: g.xmin - 2, y0: g.ymin - 0.2, x1: g.xmax + 2, y1: g.ymax + 0.2,
        line: { color: rgba(colors.gangOutline, 0.55), width: 0.7 },
      })
      annotations.push({
        x: (g.xmin + g.xmax) / 2, y: g.ymax + 1.3, text: String(g.die),
        showarrow: false, font: { size: 8, color: colors.gangLabel },
      })
    }
  }

  const layout: Record<string, unknown> = {
    paper_bgcolor: colors.surface,
    plot_bgcolor: colors.surface,
    font: { family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Arial, sans-serif", color: colors.text2, size: 11 },
    margin: { l: 48, r: 20, t: 36, b: 44 },
    // One click on a legend entry isolates that status (hides every other
    // trace); clicking it again restores all. Double-click toggles a single
    // entry. uirevision keeps the legend selection across re-renders (wafer
    // switch, label toggle, theme change).
    legend: {
      orientation: 'h', y: 1.04, x: 0, font: { color: colors.text2 },
      itemclick: 'toggleothers', itemdoubleclick: 'toggle',
    },
    uirevision: 'wafer-map',
    hovermode: 'closest',
    hoverlabel: { bgcolor: colors.inset, bordercolor: colors.border, font: { color: colors.text, size: 11 } },
    xaxis: {
      range: AXIS_RANGE.x, title: { text: 'X (mm)' }, gridcolor: colors.borderMuted, zerolinecolor: colors.border,
      tickfont: { color: colors.text3 },
    },
    yaxis: {
      range: AXIS_RANGE.y, title: { text: 'Y (mm)' }, scaleanchor: 'x', scaleratio: 1,
      gridcolor: colors.borderMuted, zerolinecolor: colors.border, tickfont: { color: colors.text3 },
    },
    shapes,
    annotations,
    ...extraLayout,
  }
  return { data: [...chrome, ...data], layout }
}

/* Horizontal 4 mm segments: x-2 .. x+2 at y, NaN-separated so one trace draws
   every spring of a status (exactly the reference's column_stack/ravel). */
export function segmentCoordinates(x: number[], y: number[], indices: number[]): { xs: (number | null)[]; ys: (number | null)[] } {
  const xs: (number | null)[] = []
  const ys: (number | null)[] = []
  for (const i of indices) {
    xs.push(x[i] - SEGMENT_HALF_WIDTH_MM, x[i] + SEGMENT_HALF_WIDTH_MM, null)
    ys.push(y[i], y[i], null)
  }
  return { xs, ys }
}

/* springs_plot(categorical=True): one line trace per status + a near-invisible
   marker layer that carries the die / spring / status hover. */
export function buildIndividualFigure(
  reference: Reference,
  statusCodes: number[],
  states: string[],
  statusColors: Record<string, string>,
  colors: ChartColors,
  dieLabels: boolean,
): Figure {
  const data: Record<string, unknown>[] = []
  const byState: number[][] = states.map(() => [])
  statusCodes.forEach((code, i) => {
    if (byState[code]) byState[code].push(i)
  })
  states.forEach((state, code) => {
    const idx = byState[code]
    if (!idx.length) return
    const { xs, ys } = segmentCoordinates(reference.x, reference.y, idx)
    data.push({
      type: 'scattergl', mode: 'lines', x: xs, y: ys,
      line: { color: statusColors[state], width: 2 },
      name: state, hoverinfo: 'skip', connectgaps: false,
    })
  })
  const custom = reference.die.map((die, i) => [die, reference.spring[i], states[statusCodes[i]] ?? 'Uninspected'])
  data.push({
    type: 'scattergl', mode: 'markers', x: reference.x, y: reference.y,
    marker: { size: 5, opacity: 0.015, color: '#111111' },
    customdata: custom,
    hovertemplate: 'Die %{customdata[0]} | Spring %{customdata[1]}<br>Status: %{customdata[2]}<extra></extra>',
    showlegend: false, name: 'Springs',
  })
  return decorate(data, reference, colors, dieLabels)
}

/* springs_plot(categorical=False): continuous color by defect frequency.
   Never-inspected springs are drawn at 0 for rendering only (the reference did
   stack.Defect_Rate.fillna(0)); their hover says so instead of showing 0.0 %. */
export function buildStackedFigure(
  reference: Reference,
  defectRate: (number | null)[],
  colors: ChartColors,
  dieLabels: boolean,
): Figure {
  const values = defectRate.map((v) => (v === null ? 0 : v))
  const custom = reference.die.map((die, i) => {
    const v = defectRate[i]
    return [die, reference.spring[i], v === null ? 'uninspected (no coverage)' : `${(v * 100).toFixed(1)}%`]
  })
  const data: Record<string, unknown>[] = [
    {
      type: 'scattergl', mode: 'markers', x: reference.x, y: reference.y,
      marker: {
        size: 5, color: values, colorscale: 'YlOrRd', cmin: 0, cmax: 1,
        colorbar: { title: { text: 'Defect frequency' }, tickfont: { color: colors.text3 }, outlinewidth: 0 },
      },
      customdata: custom,
      hovertemplate: 'Die %{customdata[0]} | Spring %{customdata[1]}<br>Defect rate %{customdata[2]}<extra></extra>',
      name: 'Observed frequency', showlegend: false,
    },
  ]
  return decorate(data, reference, colors, dieLabels)
}

/* Layout preview: every spring as a neutral 4 mm segment (no inspection data),
   with gang outlines and labels, so a coordinate file can be checked before
   it is saved. */
export type LayoutGeometry = Pick<Reference, 'die' | 'spring' | 'x' | 'y' | 'gangs'>

export function buildLayoutFigure(layout: LayoutGeometry, colors: ChartColors, dieLabels: boolean): Figure {
  const reference = layout as Reference
  const indices = layout.x.map((_v, i) => i)
  const { xs, ys } = segmentCoordinates(layout.x, layout.y, indices)
  const custom = layout.die.map((die, i) => [die, layout.spring[i]])
  const data: Record<string, unknown>[] = [
    {
      type: 'scattergl', mode: 'lines', x: xs, y: ys,
      line: { color: colors.accentFg, width: 2 },
      name: 'Spring', hoverinfo: 'skip', connectgaps: false, showlegend: false,
    },
    {
      type: 'scattergl', mode: 'markers', x: layout.x, y: layout.y,
      marker: { size: 5, opacity: 0.015, color: '#111111' },
      customdata: custom,
      hovertemplate: 'Die %{customdata[0]} | Spring %{customdata[1]}<br>X %{x:.3f} mm · Y %{y:.3f} mm<extra></extra>',
      showlegend: false, name: 'Springs',
    },
  ]
  return decorate(data, reference, colors, dieLabels, { showlegend: false })
}

/* The spatial-signature heatmap: smoothed local defect rate on the 2 mm grid,
   blank (null) where coverage is insufficient, wafer chrome without labels. */
export function buildHeatmapFigure(analysis: Analysis, reference: Reference, colors: ChartColors): Figure {
  const s = analysis.spatial
  const data: Record<string, unknown>[] = [
    {
      type: 'heatmap', x: s.bin_centers, y: s.bin_centers, z: s.rate_grid,
      zmin: 0, zmax: 1, colorscale: 'YlOrRd', hoverongaps: false,
      colorbar: { title: { text: 'Local defect rate' }, tickfont: { color: colors.text3 }, outlinewidth: 0 },
      hovertemplate: 'X %{x} mm · Y %{y} mm<br>Local defect rate %{z:.1%}<extra></extra>',
      name: 'Smoothed incidence',
    },
  ]
  return decorate(data, reference, colors, false)
}
