import { useCallback, useEffect, useRef, useState } from 'react'
import { api, UploadValidationError } from './api/client'
import type { Analysis, FileError, InspectionsResponse, Reference } from './api/types'
import { ControlsPanel } from './components/ControlsPanel'
import { ExportPanel } from './components/ExportPanel'
import { GangYieldPanel } from './components/GangYieldPanel'
import { HeaderBar } from './components/HeaderBar'
import { IndividualWaferPanel } from './components/IndividualWaferPanel'
import { KpiCards } from './components/KpiCards'
import { SpatialPanel } from './components/SpatialPanel'
import { StackedWaferPanel } from './components/StackedWaferPanel'
import { Tabs, type ViewKey } from './components/Tabs'
import { LayoutsPage } from './pages/LayoutsPage'
import { useHashRoute } from './router'
import { useChartColors } from './theme/chartColors'
import { useTheme } from './theme/useTheme'

const DEFAULT_BANDWIDTH = 5
const BANDWIDTH_DEBOUNCE_MS = 250
const VIEW_KEYS: ViewKey[] = ['individual', 'stacked', 'spatial', 'gangs', 'export']

/* Deep links: ?view=stacked opens that tab; ?session=<id> reopens an existing
   API session instead of auto-loading the synthetic examples. */
function initialView(): ViewKey {
  const requested = new URLSearchParams(window.location.search).get('view')
  return VIEW_KEYS.includes(requested as ViewKey) ? (requested as ViewKey) : 'individual'
}

function requestedSession(): string | null {
  return new URLSearchParams(window.location.search).get('session')
}

export default function App() {
  const { theme, toggle } = useTheme()
  const colors = useChartColors(theme)
  const route = useHashRoute()

  const [products, setProducts] = useState<string[]>([])
  const [examplesProduct, setExamplesProduct] = useState<string | null>(null)
  const [examplesAvailable, setExamplesAvailable] = useState(false)
  const [product, setProduct] = useState<string | null>(null)
  const [reference, setReference] = useState<Reference | null>(null)
  const [session, setSession] = useState<InspectionsResponse | null>(null)
  const [selectedWafers, setSelectedWafers] = useState<string[]>([])
  const [bandwidth, setBandwidth] = useState(DEFAULT_BANDWIDTH)
  const [showLabels, setShowLabels] = useState(true)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [view, setView] = useState<ViewKey>(initialView)
  const [individualWafer, setIndividualWafer] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState('Loading…')
  const [status, setStatus] = useState('Loading coordinate references…')
  const [error, setError] = useState<string | null>(null)
  const [fileErrors, setFileErrors] = useState<FileError[]>([])
  const bootstrapped = useRef(false)
  const skipNextProductRefresh = useRef(false)

  const fail = useCallback((prefix: string, err: unknown) => {
    if (err instanceof UploadValidationError) {
      setFileErrors(err.errors)
      setError(err.message)
    } else {
      setFileErrors([])
      setError(`${prefix}: ${err instanceof Error ? err.message : String(err)}`)
    }
    setStatus('Request could not be completed.')
  }, [])

  const loadReference = useCallback(async (p: string) => {
    setLoading(true)
    setLoadingMessage(`Loading ${p} coordinate reference…`)
    try {
      const ref = await api.reference(p)
      setReference(ref)
      setStatus(`Reference ${p}: ${ref.spring_count.toLocaleString('en-US')} springs in ${ref.gang_count} gangs.`)
      setError(null)
    } catch (err) {
      setReference(null)
      fail('Reference error', err)
    } finally {
      setLoading(false)
    }
  }, [fail])

  const adoptSession = useCallback((s: InspectionsResponse) => {
    setSession(s)
    setSelectedWafers([...s.wafers])
    setIndividualWafer(s.wafers[0] ?? '')
    setAnalysis(null)
    setFileErrors([])
    setError(null)
    setStatus(
      s.synthetic
        ? `Loaded ${s.wafers.length} SYNTHETIC example wafers (simulated data).`
        : `Loaded ${s.wafers.length} wafer${s.wafers.length === 1 ? '' : 's'} from ${s.files.length} file${s.files.length === 1 ? '' : 's'}.`,
    )
  }, [])

  const loadExamples = useCallback(async () => {
    setLoading(true)
    setLoadingMessage('Loading bundled synthetic example wafers…')
    try {
      const s = await api.loadExamples()
      if (s.product !== product) {
        setProduct(s.product)
        await loadReference(s.product)
      }
      adoptSession(s)
    } catch (err) {
      fail('Example data error', err)
    } finally {
      setLoading(false)
    }
  }, [adoptSession, fail, loadReference, product])

  const uploadFiles = useCallback(async (files: File[]) => {
    if (!product) return
    if (files.length === 0) {
      setError('Select at least one inspection file (CSV, XLSX or CloudPCS XML).')
      setFileErrors([])
      return
    }
    setLoading(true)
    setLoadingMessage(`Validating ${files.length} inspection file${files.length === 1 ? '' : 's'}…`)
    try {
      adoptSession(await api.uploadInspections(product, files))
    } catch (err) {
      fail('Upload error', err)
    } finally {
      setLoading(false)
    }
  }, [adoptSession, fail, product])

  const changeProduct = useCallback((p: string) => {
    setProduct(p)
    setSession(null)
    setAnalysis(null)
    setSelectedWafers([])
    void loadReference(p)
  }, [loadReference])

  // Bootstrap (only once the wafer map is shown): products -> reference -> (synthetic examples, when available).
  useEffect(() => {
    if (bootstrapped.current || route !== 'map') return
    bootstrapped.current = true
    skipNextProductRefresh.current = true
    ;(async () => {
      try {
        const res = await api.products()
        setProducts(res.products)
        setExamplesProduct(res.examples_product)
        setExamplesAvailable(res.examples_available)
        const existing = requestedSession()
        if (existing) {
          const s = await api.session(existing)
          setProduct(s.product)
          await loadReference(s.product)
          adoptSession(s)
          return
        }
        const first = res.examples_available ? res.examples_product : res.products[0]
        if (!first) {
          setStatus('No coordinate reference found in coordinates/.')
          setError('No product has a coordinate reference. Add coordinates/PRODUCT.xlsx or .csv to the backend.')
          return
        }
        setProduct(first)
        await loadReference(first)
        if (res.examples_available) {
          setLoading(true)
          setLoadingMessage('Loading bundled synthetic example wafers…')
          try {
            adoptSession(await api.loadExamples())
          } finally {
            setLoading(false)
          }
        }
      } catch (err) {
        fail('Startup error', err)
      }
    })()
  }, [adoptSession, fail, loadReference, route])

  // Layouts saved on the Layouts page must show up in the Product list when the user comes back.
  useEffect(() => {
    if (route !== 'map') return
    if (skipNextProductRefresh.current) {
      skipNextProductRefresh.current = false
      return
    }
    api.products()
      .then((res) => {
        setProducts(res.products)
        setExamplesAvailable(res.examples_available)
      })
      .catch(() => {
        /* the list keeps its previous value; the next action surfaces the error */
      })
  }, [route])

  // Analyze whenever the session, wafer selection or bandwidth changes (debounced for the slider).
  useEffect(() => {
    if (!session) return
    if (selectedWafers.length === 0) {
      setAnalysis(null)
      setStatus('Select at least one wafer.')
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setLoading(true)
      setLoadingMessage('Analyzing selected wafers…')
      try {
        const result = await api.analyze({ session_id: session.session_id, wafers: selectedWafers, bandwidth })
        if (cancelled) return
        setAnalysis(result)
        setError(null)
        setFileErrors([])
        setStatus(`Analysis of ${result.wafers.length} wafer${result.wafers.length === 1 ? '' : 's'} at ${bandwidth} mm bandwidth.`)
      } catch (err) {
        if (!cancelled) fail('Analysis error', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, BANDWIDTH_DEBOUNCE_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [session, selectedWafers, bandwidth, fail])

  useEffect(() => {
    if (analysis && !analysis.wafers.includes(individualWafer)) setIndividualWafer(analysis.wafers[0])
  }, [analysis, individualWafer])

  if (route === 'layouts') {
    return (
      <div className="app">
        <HeaderBar route={route} product={product} session={session} theme={theme} onToggleTheme={toggle} />
        <LayoutsPage colors={colors} />
      </div>
    )
  }

  return (
    <div className="app">
      <HeaderBar route={route} product={product} session={session} theme={theme} onToggleTheme={toggle} />
      {loading && (
        <div className="spin-overlay">
          <div>
            <span className="spinner" />
            {loadingMessage}
          </div>
        </div>
      )}
      <div className="workbench-grid">
        <ControlsPanel
          products={products}
          product={product}
          onProductChange={changeProduct}
          reference={reference}
          session={session}
          selectedWafers={selectedWafers}
          onSelectedWafersChange={setSelectedWafers}
          showLabels={showLabels}
          onShowLabelsChange={setShowLabels}
          bandwidth={bandwidth}
          onBandwidthChange={setBandwidth}
          examplesAvailable={examplesAvailable && examplesProduct !== null}
          onLoadExamples={loadExamples}
          onUpload={uploadFiles}
          loading={loading}
          status={status}
        />
        <main className={loading ? 'loading-dim' : undefined}>
          {products.length === 0 && !loading && (
            <div className="warning-banner" role="note">
              <div>⚠ No layout is saved yet. <a href="#/layouts">Open the Layouts page</a> to upload a coordinate file before loading inspections.</div>
            </div>
          )}
          <div className="caveat-note" data-testid="scope-caveat">
            <strong>Exploratory screening utility, not a validated manufacturing release decision system.</strong>{' '}
            Spatial signatures are descriptive, not causal; spiral recognition is not automated; the coordinate
            center (bounding-box midpoint) and notch-down orientation are assumed and must be validated against
            physical fiducials. Missing spring observations stay uninspected and are never counted as Good.
          </div>
          {session?.synthetic && (
            <div className="warning-banner" role="note" data-testid="synthetic-banner">
              <div>⚠ The loaded wafers are the bundled <strong>SYNTHETIC</strong> examples: explicitly simulated inspection data. Do not interpret them as measured yield.</div>
            </div>
          )}
          {error && (
            <div className="error-banner" role="alert">
              {error}
              {fileErrors.length > 0 && (
                <ul data-testid="file-errors">
                  {fileErrors.map((e) => (
                    <li key={`${e.filename}:${e.error}`}><strong>{e.filename}</strong> — {e.error}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {!analysis && !error && (
            <div className="empty-state">
              {session
                ? selectedWafers.length === 0
                  ? 'Select at least one wafer.'
                  : 'Analyzing…'
                : 'Upload one or more inspection files to begin, or load the bundled synthetic examples.'}
              {reference && !session && (
                <div className="chart-note" style={{ marginTop: 10 }}>
                  Reference {reference.product}: {reference.spring_count.toLocaleString('en-US')} springs in{' '}
                  {reference.gang_count} gangs. {reference.caveat}
                </div>
              )}
            </div>
          )}
          {analysis && reference && (
            <>
              <KpiCards analysis={analysis} />
              <Tabs active={view} onChange={setView} />
              {view === 'individual' && (
                <IndividualWaferPanel
                  analysis={analysis}
                  reference={reference}
                  wafer={individualWafer}
                  onWaferChange={setIndividualWafer}
                  showLabels={showLabels}
                  colors={colors}
                />
              )}
              {view === 'stacked' && (
                <StackedWaferPanel analysis={analysis} reference={reference} showLabels={showLabels} colors={colors} />
              )}
              {view === 'spatial' && <SpatialPanel analysis={analysis} reference={reference} colors={colors} />}
              {view === 'gangs' && <GangYieldPanel analysis={analysis} />}
              {view === 'export' && <ExportPanel analysis={analysis} />}
              <div className="footer-note">
                Pure rendering client for the extracted spring-wafer engine · coordinates centered on the reference
                bounding-box midpoint ({reference.center.x.toFixed(3)}, {reference.center.y.toFixed(3)}) mm, notch down
                assumed · springs drawn as 4 mm horizontal segments.
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
