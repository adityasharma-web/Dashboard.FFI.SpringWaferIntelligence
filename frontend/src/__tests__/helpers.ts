/* Small, hand-built API payloads: a 2-gang x 10-spring reference and a
   two-wafer analysis. Values are chosen so the rendered numbers are easy to
   assert on; nothing here is computed in the frontend. */

import type { Analysis, InspectionsResponse, ProductsResponse, Reference } from '../api/types'

export const PRODUCT = 'TEST-PROD'

export function makeReference(): Reference {
  const die: number[] = []
  const spring: number[] = []
  const x: number[] = []
  const y: number[] = []
  for (const d of [1, 2]) {
    for (let s = 1; s <= 10; s++) {
      die.push(d)
      spring.push(s)
      x.push(d === 1 ? -30 : 30)
      y.push(50 - s * 4)
    }
  }
  return {
    product: PRODUCT,
    spring_count: 20,
    gang_count: 2,
    center: { x: 71.245, y: -0.5015 },
    die,
    spring,
    x,
    y,
    gangs: [
      { die: 1, xmin: -30, xmax: -30, ymin: 10, ymax: 46 },
      { die: 2, xmin: 30, xmax: 30, ymin: 10, ymax: 46 },
    ],
    caveat: 'Coordinate center inferred from extents: X=71.245, Y=-0.502 mm. Notch down assumed.',
  }
}

export function makeProducts(): ProductsResponse {
  return { products: [PRODUCT], examples_product: PRODUCT, examples_available: true }
}

export function makeSession(synthetic = true, statusModel: 'severity' | 'defect_code' = 'severity'): InspectionsResponse {
  return {
    session_id: 'sess-1',
    product: PRODUCT,
    source: synthetic ? 'synthetic_examples' : 'upload',
    status_model: statusModel,
    synthetic,
    wafers: ['W1', 'W2'],
    files: [
      { filename: 'W1.csv', wafer_id: 'W1', observations: 20 },
      { filename: 'W2.csv', wafer_id: 'W2', observations: 18 },
    ],
  }
}

export function makeAnalysis(wafers: string[] = ['W1', 'W2'], bandwidth = 5): Analysis {
  // W1: spring (1,1) Killer, (1,2) Low; W2: (1,1) Med, springs (2,9) and (2,10) uninspected.
  const w1 = new Array(20).fill(0)
  w1[0] = 3
  w1[1] = 1
  const w2 = new Array(20).fill(0)
  w2[0] = 2
  w2[18] = 4
  w2[19] = 4
  const inspected = new Array(20).fill(2)
  inspected[18] = 1
  inspected[19] = 1
  const defects = new Array(20).fill(0)
  defects[0] = 2
  defects[1] = 1
  const killer = new Array(20).fill(0)
  killer[0] = 1
  const rate = inspected.map((n, i) => (n > 0 ? defects[i] / n : null))
  const grid = Array.from({ length: 102 }, () => Array.from({ length: 102 }, () => null as number | null))
  grid[50][40] = 0.25
  return {
    session_id: 'sess-1',
    product: PRODUCT,
    source: 'synthetic_examples',
    synthetic: true,
    status_model: 'severity',
    wafers,
    bandwidth,
    states: ['Good', 'Low', 'Med', 'Killer', 'Uninspected'],
    colors: { Good: '#21a653', Low: '#f4d43b', Med: '#f38a24', Killer: '#df3537', Uninspected: '#aab4c2' },
    status_counts: [{ status: 'Good', count: 35 }, { status: 'Low', count: 1 }, { status: 'Med', count: 1 }, { status: 'Killer', count: 1 }],
    header: { wafers: wafers.length, springs_in_reference: 20, observations: 38, bad: 3, defect_rate: 3 / 38 },
    individual: [
      { wafer_id: 'W1', status_codes: w1, counts: [{ status: 'Good', count: 18 }, { status: 'Killer', count: 1 }, { status: 'Low', count: 1 }], uninspected: 0 },
      { wafer_id: 'W2', status_codes: w2, counts: [{ status: 'Good', count: 17 }, { status: 'Med', count: 1 }], uninspected: 2 },
    ].filter((w) => wafers.includes(w.wafer_id)),
    stacked: {
      die: [...Array(10).fill(1), ...Array(10).fill(2)],
      spring: [...Array.from({ length: 10 }, (_, i) => i + 1), ...Array.from({ length: 10 }, (_, i) => i + 1)],
      inspected,
      defects,
      killer,
      defect_rate: rate,
      uninspected_springs: 0,
    },
    spatial: {
      bin_edges: Array.from({ length: 103 }, (_, i) => -102 + 2 * i),
      bin_centers: Array.from({ length: 102 }, (_, i) => -101 + 2 * i),
      rate_grid: grid,
      baseline: 3 / 38,
      peaks: [{ X_mm: -21, Y_mm: 1, Local_defect_rate: 0.25, Excess_vs_global: 0.171 }],
      recurrence: [{ die: 1, spring: 1, inspected: 2, defects: 2, q: 0.0123, p: 0.0062 }],
      recurrence_total_rows: 18,
      recurrence_min_inspected: 2,
      recurrence_tested: true,
    },
    signature: {
      zones: [
        { zone: 'Core (0-35)', inspected: 10, defects: 1, defect_rate: 0.1 },
        { zone: 'Mid (35-65)', inspected: 28, defects: 2, defect_rate: 0.0714 },
        { zone: 'Outer (65-85)', inspected: 0, defects: 0, defect_rate: 0 },
        { zone: 'Edge (85-100)', inspected: 0, defects: 0, defect_rate: 0 },
      ],
      sectors: Array.from({ length: 12 }, (_, i) => ({ sector: `sector-${i}`, defect_rate: null, size: 0 })),
      messages: [
        'No strong edge/sector indicator under current heuristic thresholds; inspect stack and hotspots.',
        'Spiral patterns require visual and model-based validation across multiple wafers; this utility does not assign a spiral label automatically.',
      ],
    },
    gang_yield: {
      rows: [
        { wafer_id: 'W1', die: 1, inspected: 10, bad: 2, total_springs: 10, bad_pct: 0.2, complete: true, disposition: 'PASS' },
        { wafer_id: 'W1', die: 2, inspected: 10, bad: 0, total_springs: 10, bad_pct: 0, complete: true, disposition: 'PASS' },
        { wafer_id: 'W2', die: 1, inspected: 10, bad: 7, total_springs: 10, bad_pct: 0.7, complete: true, disposition: 'SCRAP' },
        { wafer_id: 'W2', die: 2, inspected: 8, bad: 0, total_springs: 10, bad_pct: 0, complete: false, disposition: 'INCOMPLETE' },
      ].filter((r) => wafers.includes(r.wafer_id)) as Analysis['gang_yield']['rows'],
      scrapped: wafers.includes('W2') ? 1 : 0,
      total: wafers.length * 2,
      threshold: 0.6,
      rule: 'Scrap when bad springs / total springs in gang > 60%. Incomplete inspections are flagged; observed bad counts can already establish scrap.',
    },
    caveats: {
      scope: 'Exploratory screening utility, not a validated manufacturing release decision system.',
      signatures: 'Edge enrichment, sector asymmetry and local hotspots are descriptive signatures, not causal diagnoses.',
      spiral: 'Spiral recognition is not automatically implemented or validated.',
      registration: 'The coordinate center is the bounding-box midpoint of the reference extents and notch-down orientation is assumed.',
      line_width: 'The physical spring footprint is 4.0 x 0.4 mm; the rendered line thickness is screen-pixel-based.',
      uninspected: 'Missing spring observations are not counted as Good; they remain uninspected and are excluded from rates.',
      stacked_map: 'The stacked map draws never-inspected springs at zero for rendering only.',
      recurrence: 'Exact binomial enrichment tests with Benjamini-Hochberg exploratory q-values; interpret cautiously.',
      heatmap: 'Gaussian-smoothed defect counts divided by Gaussian-smoothed inspection exposure. Blank areas have insufficient coverage.',
      export: 'Coordinates are product-referenced; severity and defect observations are inspection-file values, never synthesized by the application.',
      synthetic: 'The bundled example wafers are explicitly simulated; do not interpret them as measured yield.',
    },
  }
}

/* A CloudPCS-style single-wafer analysis: Good + defect codes H8 / XL, no severity. */
export function makeDefectCodeAnalysis(): Analysis {
  const base = makeAnalysis(['W304617.1'])
  const codes = new Array(20).fill(0)
  codes[0] = 1 // H8
  codes[1] = 1 // H8
  codes[2] = 2 // XL
  codes[19] = 3 // uninspected
  return {
    ...base,
    source: 'upload',
    synthetic: false,
    status_model: 'defect_code',
    states: ['Good', 'H8', 'XL', 'Uninspected'],
    colors: { Good: '#21a653', H8: '#df3537', XL: '#f38a24', Uninspected: '#aab4c2' },
    status_counts: [{ status: 'Good', count: 16 }, { status: 'H8', count: 2 }, { status: 'XL', count: 1 }],
    header: { wafers: 1, springs_in_reference: 20, observations: 19, bad: 3, defect_rate: 3 / 19 },
    individual: [{ wafer_id: 'W304617.1', status_codes: codes, counts: [{ status: 'Good', count: 16 }, { status: 'H8', count: 2 }, { status: 'XL', count: 1 }], uninspected: 1 }],
    stacked: { ...base.stacked, killer: new Array(20).fill(0), uninspected_springs: 1 },
  }
}

export interface FetchLog {
  url: string
  method: string
  body: unknown
}

/* A fetch stub routing the API paths the app uses. Records every call. */
export function installFetchStub(overrides: Partial<Record<string, (init?: RequestInit) => Response | Promise<Response>>> = {}) {
  const calls: FetchLog[] = []
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  const routes: Record<string, (init?: RequestInit) => Response | Promise<Response>> = {
    '/api/products': () => json(makeProducts()),
    [`/api/reference/${PRODUCT}`]: () => json(makeReference()),
    '/api/examples': () => json(makeSession(true)),
    '/api/analyze': (init) => {
      const body = JSON.parse(String(init?.body ?? '{}')) as { wafers: string[] | null; bandwidth: number }
      return json(makeAnalysis(body.wafers ?? ['W1', 'W2'], body.bandwidth))
    },
    '/api/inspections': () => json(makeSession(false)),
    ...overrides,
  }
  const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const path = url.split('?')[0]
    let body: unknown = null
    if (typeof init?.body === 'string') {
      try {
        body = JSON.parse(init.body)
      } catch {
        body = init.body
      }
    } else if (init?.body instanceof FormData) {
      body = Object.fromEntries(Array.from(init.body.entries()).map(([k, v]) => [k, v instanceof File ? v.name : v]))
    }
    calls.push({ url, method: init?.method ?? 'GET', body })
    const handler = routes[path]
    if (!handler) return json({ detail: `unhandled ${path}` }, 404)
    return handler(init)
  })
  vi.stubGlobal('fetch', stub)
  return { calls, stub }
}
