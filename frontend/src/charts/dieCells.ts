/* Die-layout rendering helpers. A die layout has one coordinate per die and
   no die dimensions, so each die is drawn as a cell at the grid pitch (92 % of
   the pitch, leaving a gap); the caption says so. When no pitch can be
   inferred (a single die) a 4 mm square is used. */

import type { Pitch } from '../api/types'

export const DIE_CELL_FILL = 0.92
export const DIE_FALLBACK_HALF_MM = 2

export interface DieCell {
  x0: number
  x1: number
  y0: number
  y1: number
}

export function dieCell(x: number, y: number, pitch: Pitch | null): DieCell {
  const hw = pitch ? (pitch.x * DIE_CELL_FILL) / 2 : DIE_FALLBACK_HALF_MM
  const hh = pitch ? (pitch.y * DIE_CELL_FILL) / 2 : DIE_FALLBACK_HALF_MM
  return { x0: x - hw, x1: x + hw, y0: y - hh, y1: y + hh }
}

/* Plotly's YlOrRd scale, so stacked die cells (layout shapes, which cannot use
   a trace colorscale) match the colorbar and the spring map exactly. */
const YLORRD: [number, [number, number, number]][] = [
  [0, [255, 255, 204]], [0.125, [255, 237, 160]], [0.25, [254, 217, 118]], [0.375, [254, 178, 76]],
  [0.5, [253, 141, 60]], [0.625, [252, 78, 42]], [0.75, [227, 26, 28]], [0.875, [189, 0, 38]], [1, [128, 0, 38]],
]

export function ylOrRd(value: number): string {
  const v = Math.min(1, Math.max(0, value))
  for (let i = 1; i < YLORRD.length; i++) {
    const [p1, c1] = YLORRD[i]
    if (v <= p1) {
      const [p0, c0] = YLORRD[i - 1]
      const t = p1 === p0 ? 0 : (v - p0) / (p1 - p0)
      const c = c0.map((a, k) => Math.round(a + (c1[k] - a) * t))
      return `rgb(${c[0]},${c[1]},${c[2]})`
    }
  }
  const last = YLORRD[YLORRD.length - 1][1]
  return `rgb(${last[0]},${last[1]},${last[2]})`
}
