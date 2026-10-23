import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LayoutItem, LayoutPreview } from '../api/types'
import App from '../App'
import { buildLayoutFigure } from '../charts/waferFigures'
import { navigate, routeFromHash } from '../router'
import { reactCalls } from '../test/plotlyStub'
import { resolveChartColors } from '../theme/chartColors'
import { installFetchStub, makeReference } from './helpers'

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
      center_x: 71.245, center_y: -0.5015, x_min: 0, x_max: 142.49, y_min: -80, y_max: 79, max_radius_mm: 81.1, warnings: [],
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
      warnings: ['Gangs do not all have the same spring count (9 to 10). Gang yield uses each gang\'s own count.'],
    },
    die: ref.die, spring: ref.spring, x: ref.x, y: ref.y, gangs: ref.gangs,
    caveat: 'Coordinate center inferred from extents: X=17.750, Y=89.000 mm. Notch down assumed.',
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
