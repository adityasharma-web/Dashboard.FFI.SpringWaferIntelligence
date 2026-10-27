import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LayoutItem, LayoutPreview } from '../api/types'
import App from '../App'
import { buildIndividualFigure, buildLayoutFigure, buildStackedFigure } from '../charts/waferFigures'
import { navigate, routeFromHash } from '../router'
import { reactCalls } from '../test/plotlyStub'
import { resolveChartColors } from '../theme/chartColors'
import { installFetchStub, makeAnalysis, makeReference } from './helpers'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function makeLayoutItem(overrides: Partial<LayoutItem> = {}): LayoutItem {
  return {
    name: '152-900530D',
    file: '152-900530D.xlsx',
    products: ['152-900530D'],
    implicit: true,
    saved_at: null,
    source_filename: null,
    size_bytes: 614794,
    summary: {
      springs: 20952, gangs: 108, springs_per_gang_min: 194, springs_per_gang_max: 194,
      center_x: 71.245, center_y: -0.5015, x_min: 0, x_max: 142.49, y_min: -80, y_max: 79, max_radius_mm: 81.1,
      kind: 'spring', units: 'mm', pitch_x_mm: null, pitch_y_mm: null, warnings: [],
    },
    error: null,
    ...overrides,
  }
}

function makePreview(): LayoutPreview {
  const ref = makeReference()
  return {
    filename: 'NEW-LAYOUT.csv',
    suggested_name: 'NEW-LAYOUT',
    summary: {
      springs: 20, gangs: 2, springs_per_gang_min: 10, springs_per_gang_max: 10,
      center_x: 17.75, center_y: 89, x_min: 10.5, x_max: 25, y_min: 80, y_max: 98, max_radius_mm: 48.3,
      kind: 'spring', units: 'mm', pitch_x_mm: null, pitch_y_mm: null,
      warnings: ['Gangs do not all have the same spring count (9 to 10). Gang yield uses each gang\'s own count.'],
    },
    kind: 'spring',
    pitch: null,
    die: ref.die, spring: ref.spring, x: ref.x, y: ref.y, gangs: ref.gangs,
    caveat: 'Coordinate center inferred from extents: X=17.750, Y=89.000 mm. Notch down assumed.',
  }
}

/* A die-only layout in the shape of 159-511159A.csv: four dies, pitch 21.03 × 10.36 mm, read from µm. */
function makeDiePreview(): LayoutPreview {
  const x = [-21.03, 0, 21.03, 0]
  const y = [-5.18, -5.18, -5.18, 5.18]
  return {
    filename: '159-511159A.csv',
    suggested_name: '159-511159A',
    summary: {
      springs: 4, gangs: 4, springs_per_gang_min: 1, springs_per_gang_max: 1,
      center_x: 0, center_y: 5.18, x_min: -21.03, x_max: 21.03, y_min: 0, y_max: 10.36, max_radius_mm: 21.7,
      kind: 'die', units: 'um->mm', pitch_x_mm: 21.03251, pitch_y_mm: 10.3646837,
      warnings: ['Coordinates were read as micrometres (values beyond 1,000) and converted to millimetres.'],
    },
    kind: 'die',
    pitch: { x: 21.03251, y: 10.3646837 },
    die: [1, 2, 3, 4], spring: [1, 1, 1, 1], x, y,
    gangs: [1, 2, 3, 4].map((d, i) => ({ die: d, xmin: x[i], xmax: x[i], ymin: y[i], ymax: y[i] })),
    caveat: 'Coordinate center inferred from extents: X=0.000, Y=5.182 mm. Notch down assumed.',
  }
}

describe('router', () => {
  it('maps hashes to routes', () => {
    expect(routeFromHash('')).toBe('map')
    expect(routeFromHash('#/')).toBe('map')
    expect(routeFromHash('#/layouts')).toBe('layouts')
    expect(routeFromHash('#layouts')).toBe('layouts')
    expect(routeFromHash('#/layouts?x=1')).toBe('layouts')
    expect(routeFromHash('#/nope')).toBe('map')
  })
})

describe('layout preview figure', () => {
  it('draws every spring as a neutral 4 mm segment with gang outlines', () => {
    const preview = makePreview()
    const fig = buildLayoutFigure(preview, resolveChartColors('dark'), true)
    const segments = fig.data.find((t) => t.name === 'Spring') as any
    expect(segments.x).toHaveLength(20 * 3)
    expect(segments.x.slice(0, 3)).toEqual([-32, -28, null])
    expect(segments.showlegend).toBe(false)
    const hover = fig.data.find((t) => t.name === 'Springs') as any
    expect(hover.customdata[0]).toEqual([1, 1])
    expect((fig.layout as any).shapes).toHaveLength(2)
    expect((fig.layout as any).showlegend).toBe(false)
    expect((buildLayoutFigure(preview, resolveChartColors('dark'), false).layout as any).shapes).toHaveLength(0)
  })
})

describe('die layout figures', () => {
  it('draws one cell per die at the grid pitch, colored by status', () => {
    const preview = makeDiePreview()
    const colors = resolveChartColors('dark')
    const layoutFig = buildLayoutFigure(preview, colors, true)
    const shapes = (layoutFig.layout as any).shapes
    expect(shapes).toHaveLength(4)
    expect(shapes[0].x1 - shapes[0].x0).toBeCloseTo(21.03251 * 0.92, 5)
    expect(shapes[0].y1 - shapes[0].y0).toBeCloseTo(10.3646837 * 0.92, 5)
    expect((layoutFig.layout as any).annotations.map((a: any) => a.text)).toEqual(['1', '2', '3', '4'])

    const reference = { ...makeReference(), ...preview, product: 'DIE', spring_count: 4, gang_count: 4, center: { x: 0, y: 5.18 } }
    const fig = buildIndividualFigure(reference, [0, 3, 0, 4], ['Good', 'Low', 'Med', 'Killer', 'Uninspected'], makeAnalysis().colors, colors, false)
    const cells = (fig.layout as any).shapes
    expect(cells.map((c: any) => c.fillcolor)).toEqual(['#21a653', '#df3537', '#21a653', '#aab4c2'])
    expect(fig.data.filter((t) => t.name === 'Good' || t.name === 'Killer' || t.name === 'Uninspected')).toHaveLength(3)
    expect(fig.data.some((t) => t.name === 'Low')).toBe(false)
    expect((fig.layout as any).annotations).toHaveLength(0)

    const stacked = buildStackedFigure(reference, [0, 0.5, 1, null], colors, true)
    const fills = (stacked.layout as any).shapes.map((c: any) => c.fillcolor)
    expect(fills[0]).toBe('rgb(255,255,204)')
    expect(fills[2]).toBe('rgb(128,0,38)')
    expect(fills[3]).toBe('#aab4c2')
    expect((stacked.data.find((t) => t.name === 'Observed frequency') as any).marker.showscale).toBe(true)
  })
})

describe('Layouts page', () => {
  beforeEach(() => {
    reactCalls.length = 0
    localStorage.clear()
    window.location.hash = '#/layouts'
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    window.location.hash = ''
  })

  it('lists saved layouts, previews an upload, saves it and refreshes the list', async () => {
    let saved = false
    const { calls } = installFetchStub({
      '/api/layouts': (init) => {
        if (init?.method === 'POST') {
          saved = true
          return json(makeLayoutItem({ name: 'NEW-LAYOUT', file: 'NEW-LAYOUT.csv', products: ['152-900999A', '152-900999B'], implicit: false, saved_at: '2026-10-22T15:00:00+00:00', source_filename: 'NEW-LAYOUT.csv', summary: { ...makePreview().summary, warnings: [] } }))
        }
        return json({ layouts: saved ? [makeLayoutItem({ name: 'NEW-LAYOUT', products: ['152-900999A', '152-900999B'], implicit: false }), makeLayoutItem()] : [makeLayoutItem()] })
      },
      '/api/layouts/preview': () => json(makePreview()),
    })
    render(<App />)

    const table = await screen.findByTestId('layouts-table')
    expect(within(table).getAllByText('152-900530D')).toHaveLength(2) // layout name + product name
    expect(within(table).getByText('20,952')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Layouts' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('tablist', { name: 'Views' })).not.toBeInTheDocument()
    expect(calls.map((c) => c.url)).not.toContain('/api/examples')

    const input = screen.getByLabelText(/Coordinate file/) as HTMLInputElement
    await userEvent.upload(input, new File(['Die_Num,Spring_Num,X,Y\n1,1,0,0\n'], 'NEW-LAYOUT.csv', { type: 'text/csv' }))
    expect(await screen.findByTestId('layout-map')).toBeInTheDocument()
    expect(screen.getByTestId('preview-warnings')).toHaveTextContent('same spring count')
    expect(screen.getByLabelText('Layout name')).toHaveValue('NEW-LAYOUT')
    expect(screen.getByLabelText(/Design \/ product names/)).toHaveValue('NEW-LAYOUT')
    expect(screen.getByText('Preview · not saved yet')).toBeInTheDocument()
    const last = reactCalls[reactCalls.length - 1]
    expect((last.data.find((t) => t.name === 'Spring') as any).x).toHaveLength(60)

    await userEvent.clear(screen.getByLabelText(/Design \/ product names/))
    await userEvent.type(screen.getByLabelText(/Design \/ product names/), '152-900999A, 152-900999B')
    await userEvent.click(screen.getByTestId('save-layout'))
    expect(await screen.findByTestId('saved-banner')).toHaveTextContent('Saved layout NEW-LAYOUT')
    expect(screen.getByText('Preview · saved as NEW-LAYOUT')).toBeInTheDocument()
    expect(screen.getByTestId('save-layout')).toBeDisabled()
    expect(screen.queryByTestId('name-taken')).not.toBeInTheDocument()
    const save = calls.find((c) => c.url === '/api/layouts' && c.method === 'POST')
    expect(save?.body).toEqual({ file: 'NEW-LAYOUT.csv', name: 'NEW-LAYOUT', products: '152-900999A, 152-900999B', replace: 'false' })
    await waitFor(() => expect(within(screen.getByTestId('layouts-table')).getByText('152-900999A, 152-900999B')).toBeInTheDocument())
  })

  it('previews a die-only layout with its own tiles', async () => {
    installFetchStub({
      '/api/layouts': () => json({ layouts: [makeLayoutItem()] }),
      '/api/layouts/preview': () => json(makeDiePreview()),
    })
    render(<App />)
    await screen.findByTestId('layouts-table')
    await userEvent.upload(screen.getByLabelText(/Coordinate file/), new File(['Die #,X,Y\n1,0,0\n'], '159-511159A.csv', { type: 'text/csv' }))
    await screen.findByTestId('layout-map')
    expect(screen.getByTestId('preview-kind')).toHaveTextContent('Die map')
    expect(screen.getByText('Grid pitch')).toBeInTheDocument()
    expect(screen.getByText('µm → mm')).toBeInTheDocument()
    expect(screen.getByTestId('preview-warnings')).toHaveTextContent('micrometres')
    expect(screen.getByText(/Die layout \(no spring level\)/)).toBeInTheDocument()
  })

  it('requires Replace for an existing name and shows save errors', async () => {
    installFetchStub({
      '/api/layouts': (init) =>
        init?.method === 'POST'
          ? json({ detail: "A layout named '152-900530D' already exists (152-900530D.xlsx). Tick 'Replace existing layout' to overwrite it." }, 422)
          : json({ layouts: [makeLayoutItem()] }),
      '/api/layouts/preview': () => json({ ...makePreview(), suggested_name: '152-900530D' }),
    })
    render(<App />)
    await screen.findByTestId('layouts-table')
    await userEvent.upload(screen.getByLabelText(/Coordinate file/), new File(['x'], '152-900530D.csv', { type: 'text/csv' }))
    await screen.findByTestId('layout-map')
    expect(screen.getByTestId('name-taken')).toBeInTheDocument()
    expect(screen.getByTestId('save-layout')).toBeDisabled()
    await userEvent.click(screen.getByLabelText(/Replace existing layout/))
    expect(screen.getByTestId('save-layout')).toBeEnabled()
    await userEvent.click(screen.getByTestId('save-layout'))
    expect(await screen.findByTestId('save-error')).toHaveTextContent('already exists')
  })

  it('shows parse errors from the preview and deletes with confirmation', async () => {
    const { calls } = installFetchStub({
      '/api/layouts': () => json({ layouts: [makeLayoutItem()] }),
      '/api/layouts/preview': () => json({ detail: "Reference must contain {'Die_Num', 'Spring_Num', 'X', 'Y'}. Found: ['Die_Num', 'Spring_Num', 'X']" }, 422),
      '/api/layouts/152-900530D': () => json({ name: '152-900530D', file: '152-900530D.xlsx', products: ['152-900530D'] }),
    })
    render(<App />)
    await screen.findByTestId('layouts-table')
    await userEvent.upload(screen.getByLabelText(/Coordinate file/), new File(['x'], 'bad.csv', { type: 'text/csv' }))
    expect(await screen.findByTestId('preview-error')).toHaveTextContent('Reference must contain')
    expect(screen.queryByTestId('layout-map')).not.toBeInTheDocument()

    await userEvent.click(screen.getByTestId('delete-152-900530D'))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await userEvent.click(screen.getByTestId('confirm-delete-152-900530D'))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.url === '/api/layouts/152-900530D')).toBe(true))
  })

  it('does not bootstrap the wafer map while on the layouts page, then does so on navigation', async () => {
    const { calls } = installFetchStub({ '/api/layouts': () => json({ layouts: [makeLayoutItem()] }) })
    render(<App />)
    await screen.findByTestId('layouts-table')
    expect(calls.map((c) => c.url)).toEqual(['/api/layouts'])
    navigate('map')
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await waitFor(() => expect(screen.getByRole('tablist', { name: 'Views' })).toBeInTheDocument(), { timeout: 4000 })
    expect(screen.getByRole('link', { name: 'Wafer map' })).toHaveAttribute('aria-current', 'page')
    expect(calls.filter((c) => c.url === '/api/products')).toHaveLength(1)
  })

  it('refreshes the product list when returning to the wafer map', async () => {
    window.location.hash = ''
    const { calls } = installFetchStub({ '/api/layouts': () => json({ layouts: [makeLayoutItem()] }) })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('tablist', { name: 'Views' })).toBeInTheDocument(), { timeout: 4000 })
    expect(calls.filter((c) => c.url === '/api/products')).toHaveLength(1)
    navigate('layouts')
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await screen.findByTestId('layouts-table')
    navigate('map')
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await waitFor(() => expect(calls.filter((c) => c.url === '/api/products')).toHaveLength(2))
    expect(screen.getByRole('tablist', { name: 'Views' })).toBeInTheDocument()
  })
})
