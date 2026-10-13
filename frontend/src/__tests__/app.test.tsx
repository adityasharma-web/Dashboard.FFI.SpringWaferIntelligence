import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { reactCalls } from '../test/plotlyStub'
import { installFetchStub } from './helpers'

async function renderApp(overrides?: Parameters<typeof installFetchStub>[0]) {
  const stub = installFetchStub(overrides)
  render(<App />)
  await waitFor(() => expect(screen.getByRole('tablist', { name: 'Views' })).toBeInTheDocument(), { timeout: 4000 })
  return stub
}

describe('App bootstrap and header metrics', () => {
  beforeEach(() => {
    reactCalls.length = 0
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads products, the reference and the synthetic examples, then analyzes', async () => {
    const { calls } = await renderApp()
    const paths = calls.map((c) => c.url.split('?')[0])
    expect(paths.slice(0, 3)).toEqual(['/api/products', '/api/reference/TEST-PROD', '/api/examples'])
    expect(paths).toContain('/api/analyze')
    const analyze = calls.find((c) => c.url === '/api/analyze')
    expect(analyze?.body).toEqual({ session_id: 'sess-1', wafers: ['W1', 'W2'], bandwidth: 5 })

    expect(screen.getByTestId('source-badge')).toHaveTextContent('SYNTHETIC example data')
    expect(screen.getByTestId('synthetic-banner')).toHaveTextContent('explicitly simulated')
    expect(screen.getByTestId('scope-caveat')).toHaveTextContent('not a validated manufacturing release decision system')
    expect(screen.getByTestId('center-caveat')).toHaveTextContent('X=71.245, Y=-0.502 mm. Notch down assumed.')

    const kpis = screen.getByLabelText('Header metrics')
    expect(within(kpis).getByText('Wafers').nextSibling).toHaveTextContent('2')
    expect(within(kpis).getByText('Springs in reference').nextSibling).toHaveTextContent('20')
    expect(within(kpis).getByText('Inspected observations').nextSibling).toHaveTextContent('38')
    expect(within(kpis).getByText('Defect rate').nextSibling).toHaveTextContent('7.9%')
  })

  it('shows the individual wafer view by default with the counts table and the uninspected row', async () => {
    await renderApp()
    expect(screen.getByTestId('individual-map')).toBeInTheDocument()
    const last = reactCalls[reactCalls.length - 1]
    expect(last.data.some((t) => t.name === 'Killer')).toBe(true)
    const counts = screen.getByTestId('status-counts')
    expect(within(counts).getByText('Killer').closest('tr')).toHaveTextContent('1')
    expect(within(counts).getByText(/Uninspected \(reference springs/).closest('tr')).toHaveTextContent('0')

    await userEvent.selectOptions(screen.getByLabelText('Wafer ID'), 'W2')
    expect(screen.getByRole('heading', { name: /TEST-PROD · W2/ })).toBeInTheDocument()
    expect(within(screen.getByTestId('status-counts')).getByText(/Uninspected \(reference springs/).closest('tr')).toHaveTextContent('2')
  })

  it('switches between the five views', async () => {
    await renderApp()
    const tabs = screen.getByRole('tablist', { name: 'Views' })
    expect(within(tabs).getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Individual wafer', 'Stacked wafer', 'Spatial signatures', 'Gang yield', 'Export',
    ])

    await userEvent.click(within(tabs).getByRole('tab', { name: 'Stacked wafer' }))
    expect(screen.getByTestId('stacked-map')).toBeInTheDocument()
    expect(screen.getByText(/displayed at zero for map rendering only/)).toBeInTheDocument()
    expect(screen.getByTestId('stacked-table')).toBeInTheDocument()

    await userEvent.click(within(tabs).getByRole('tab', { name: 'Spatial signatures' }))
    expect(screen.getByTestId('heatmap')).toBeInTheDocument()
    expect(screen.getByTestId('indicator-messages')).toHaveTextContent('does not assign a spiral label automatically')
    expect(screen.getByTestId('zones-table')).toHaveTextContent('Core (0-35)')
    expect(screen.getByTestId('hotspots-table')).toHaveTextContent('0.171')
    expect(screen.getByTestId('recurrence-table')).toHaveTextContent('0.0123')
    expect(screen.getByText(/Benjamini-Hochberg exploratory q-values/)).toBeInTheDocument()

    await userEvent.click(within(tabs).getByRole('tab', { name: 'Gang yield' }))
    expect(screen.getByTestId('gang-rule')).toHaveTextContent('> 60%')
    expect(screen.getByTestId('gang-rule')).toHaveTextContent('60% exactly is not scrap')
    expect(screen.getByTestId('scrapped-metric')).toHaveTextContent('1')
    const gangTable = screen.getByTestId('gang-table')
    expect(within(gangTable).getByText('SCRAP')).toBeInTheDocument()
    expect(within(gangTable).getByText('INCOMPLETE')).toBeInTheDocument()
    expect(within(gangTable).getAllByText('PASS')).toHaveLength(2)

    await userEvent.click(within(tabs).getByRole('tab', { name: 'Export' }))
    const stacked = screen.getByTestId('export-stacked') as HTMLAnchorElement
    expect(stacked.getAttribute('href')).toBe('/api/export/stacked?session_id=sess-1&wafers=W1&wafers=W2')
    expect(screen.getByTestId('export-inspection').getAttribute('href')).toBe('/api/export/inspection?session_id=sess-1&wafers=W1&wafers=W2')
    expect(screen.getByText(/never synthesized by the application/)).toBeInTheDocument()
  })
})

describe('App controls', () => {
  beforeEach(() => {
    reactCalls.length = 0
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('re-analyzes the selected wafer subset and bandwidth', async () => {
    const { calls } = await renderApp()
    await userEvent.click(screen.getByLabelText('W2'))
    await waitFor(() => {
      const last = calls.filter((c) => c.url === '/api/analyze').at(-1)
      expect(last?.body).toEqual({ session_id: 'sess-1', wafers: ['W1'], bandwidth: 5 })
    })
    await waitFor(() => expect(within(screen.getByLabelText('Header metrics')).getByText('Wafers').nextSibling).toHaveTextContent('1'))

    const slider = screen.getByLabelText('Spatial smoothing bandwidth') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '9' } })
    await waitFor(() => {
      const last = calls.filter((c) => c.url === '/api/analyze').at(-1)
      expect(last?.body).toEqual({ session_id: 'sess-1', wafers: ['W1'], bandwidth: 9 })
    })
    expect(screen.getByText('9 mm')).toBeInTheDocument()
  })

  it('toggles gang outlines without a new API request', async () => {
    const { calls } = await renderApp()
    const before = calls.length
    const callsBefore = reactCalls.length
    await userEvent.click(screen.getByLabelText('Show gang outlines and labels'))
    await waitFor(() => expect(reactCalls.length).toBeGreaterThan(callsBefore))
    expect((reactCalls[reactCalls.length - 1].layout as any).shapes).toHaveLength(0)
    expect(calls.length).toBe(before)
  })

  it('lists every per-file validation error and loads nothing', async () => {
    await renderApp({
      '/api/inspections': () =>
        new Response(
          JSON.stringify({
            detail: '2 file(s) failed validation; nothing was loaded.',
            errors: [
              { filename: 'wrong.csv', error: 'wrong.csv: product mismatch; expected TEST-PROD' },
              { filename: 'real.xml', error: "real.xml: no coordinate reference for product '152-900405V'" },
            ],
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
    })
    const input = screen.getByLabelText(/Inspection files/) as HTMLInputElement
    await userEvent.upload(input, [
      new File(['a'], 'wrong.csv', { type: 'text/csv' }),
      new File(['b'], 'real.xml', { type: 'application/xml' }),
    ])
    await userEvent.click(screen.getByRole('button', { name: 'Analyze uploads' }))
    const errors = await screen.findByTestId('file-errors')
    expect(within(errors).getAllByRole('listitem')).toHaveLength(2)
    expect(errors).toHaveTextContent('product mismatch')
    expect(errors).toHaveTextContent("no coordinate reference for product '152-900405V'")
    // the synthetic session is still the active one
    expect(screen.getByTestId('source-badge')).toHaveTextContent('SYNTHETIC example data')
  })

  it('requires a file selection before uploading', async () => {
    await renderApp()
    await userEvent.click(screen.getByRole('button', { name: 'Analyze uploads' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Select at least one inspection file')
  })
})
