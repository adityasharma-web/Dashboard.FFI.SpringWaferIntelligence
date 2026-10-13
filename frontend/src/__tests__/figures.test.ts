import { describe, expect, it } from 'vitest'
import {
  AXIS_RANGE,
  NOTCH,
  WAFER_RADIUS_MM,
  buildHeatmapFigure,
  buildIndividualFigure,
  buildStackedFigure,
  decorate,
  segmentCoordinates,
} from '../charts/waferFigures'
import { resolveChartColors } from '../theme/chartColors'
import { makeAnalysis, makeReference } from './helpers'

const colors = resolveChartColors('dark')
const reference = makeReference()
const analysis = makeAnalysis()

describe('wafer geometry (ported from decorate())', () => {
  it('draws a 100 mm radius wafer outline with 361 points and the bottom notch', () => {
    const fig = decorate([], reference, colors, false)
    const wafer = fig.data[0] as { x: number[]; y: number[]; name: string }
    expect(wafer.name).toBe('Wafer')
    expect(wafer.x).toHaveLength(361)
    expect(Math.max(...wafer.x)).toBeCloseTo(WAFER_RADIUS_MM, 6)
    expect(Math.min(...wafer.y)).toBeCloseTo(-WAFER_RADIUS_MM, 6)
    const notch = fig.data[1] as { x: number[]; y: number[]; fill: string }
    expect(notch.x).toEqual(NOTCH.x)
    expect(notch.y).toEqual([-99.955, -97.2, -99.955])
    expect(notch.fill).toBe('toself')
  })

  it('locks the aspect ratio and uses the reference axis ranges', () => {
    const layout = decorate([], reference, colors, false).layout as any
    expect(layout.yaxis.scaleanchor).toBe('x')
    expect(layout.yaxis.scaleratio).toBe(1)
    expect(layout.xaxis.range).toEqual(AXIS_RANGE.x)
    expect(layout.yaxis.range).toEqual([-108, 106])
    expect(layout.hovermode).toBe('closest')
  })

  it('isolates a status on a single legend click and keeps the choice across re-renders', () => {
    const layout = decorate([], reference, colors, false).layout as any
    expect(layout.legend.itemclick).toBe('toggleothers')
    expect(layout.legend.itemdoubleclick).toBe('toggle')
    expect(layout.uirevision).toBe('wafer-map')
  })

  it('pads gang outlines by 2 mm in X and 0.2 mm in Y and labels each die 1.3 mm above', () => {
    const layout = decorate([], reference, colors, true).layout as any
    expect(layout.shapes).toHaveLength(2)
    expect(layout.shapes[0]).toMatchObject({ type: 'rect', x0: -32, x1: -28, y0: 9.8, y1: 46.2 })
    expect(layout.annotations[0]).toMatchObject({ x: -30, y: 47.3, text: '1' })
    expect(layout.annotations[1].text).toBe('2')
    const none = decorate([], reference, colors, false).layout as any
    expect(none.shapes).toHaveLength(0)
    expect(none.annotations).toHaveLength(0)
  })
})

describe('individual wafer figure (springs_plot categorical)', () => {
  it('draws every spring as a 4 mm horizontal segment with NaN separators', () => {
    const { xs, ys } = segmentCoordinates([10, -5], [3, 7], [0, 1])
    expect(xs).toEqual([8, 12, null, -7, -3, null])
    expect(ys).toEqual([3, 3, null, 7, 7, null])
  })

  it('emits one line trace per present status in the domain palette plus the hover layer', () => {
    const fig = buildIndividualFigure(reference, analysis.individual[0].status_codes, analysis.states, analysis.colors, colors, true)
    const lines = fig.data.filter((t) => t.mode === 'lines' && t.type === 'scattergl') as any[]
    expect(lines.map((t) => t.name)).toEqual(['Good', 'Low', 'Killer'])
    expect(lines.find((t) => t.name === 'Killer').line.color).toBe('#df3537')
    expect(lines.find((t) => t.name === 'Good').line.color).toBe('#21a653')
    expect(lines.every((t) => t.line.width === 2)).toBe(true)
    // Killer is spring (1,1): x=-30, y=46 -> segment -32..-28
    expect(lines.find((t) => t.name === 'Killer').x).toEqual([-32, -28, null])
    const good = lines.find((t) => t.name === 'Good')
    expect(good.x).toHaveLength(18 * 3)
    const hover = fig.data.find((t) => t.mode === 'markers') as any
    expect(hover.customdata[0]).toEqual([1, 1, 'Killer'])
    expect(hover.customdata[2]).toEqual([1, 3, 'Good'])
    expect(hover.hovertemplate).toContain('Die %{customdata[0]} | Spring %{customdata[1]}')
    expect(hover.marker.opacity).toBe(0.015)
  })

  it('renders uninspected springs in gray, never as Good', () => {
    const fig = buildIndividualFigure(reference, analysis.individual[1].status_codes, analysis.states, analysis.colors, colors, false)
    const names = fig.data.filter((t) => t.mode === 'lines' && t.type === 'scattergl').map((t) => t.name)
    expect(names).toEqual(['Good', 'Med', 'Uninspected'])
    const un = fig.data.find((t) => t.name === 'Uninspected') as any
    expect(un.line.color).toBe('#aab4c2')
    expect(un.x).toHaveLength(2 * 3)
    const good = fig.data.find((t) => t.name === 'Good') as any
    expect(good.x).toHaveLength(17 * 3)
  })
})

describe('stacked wafer figure (springs_plot continuous)', () => {
  it('colors by defect frequency on YlOrRd 0..1 and marks missing coverage in the hover only', () => {
    const rate = analysis.stacked.defect_rate.slice()
    rate[19] = null
    const fig = buildStackedFigure(reference, rate, colors, true)
    const trace = fig.data.find((t) => t.name === 'Observed frequency') as any
    expect(trace.marker.colorscale).toBe('YlOrRd')
    expect(trace.marker.cmin).toBe(0)
    expect(trace.marker.cmax).toBe(1)
    expect(trace.marker.color[0]).toBe(1)
    expect(trace.marker.color[19]).toBe(0) // drawn at zero for rendering only
    expect(trace.customdata[19][2]).toBe('uninspected (no coverage)')
    expect(trace.customdata[0][2]).toBe('100.0%')
    expect(trace.customdata[1][2]).toBe('50.0%')
    expect((fig.layout as any).shapes).toHaveLength(2)
  })
})

describe('spatial heatmap figure', () => {
  it('passes the API grid through unchanged, blank where coverage is insufficient', () => {
    const fig = buildHeatmapFigure(analysis, reference, colors)
    const heat = fig.data.find((t) => t.type === 'heatmap') as any
    expect(heat.z).toBe(analysis.spatial.rate_grid)
    expect(heat.x).toBe(analysis.spatial.bin_centers)
    expect(heat.hoverongaps).toBe(false)
    expect(heat.zmin).toBe(0)
    expect(heat.zmax).toBe(1)
    expect(heat.colorscale).toBe('YlOrRd')
    expect((fig.layout as any).shapes).toHaveLength(0) // no die labels on the heatmap
  })
})
