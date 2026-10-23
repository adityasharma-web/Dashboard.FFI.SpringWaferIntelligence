import type {
  Analysis,
  AnalyzeRequest,
  FileError,
  InspectionsResponse,
  LayoutItem,
  LayoutPreview,
  LayoutSaveRequest,
  LayoutsResponse,
  ProductsResponse,
  Reference,
} from './types'

const BASE = '/api'

/* Upload validation failures carry one message per file (the reference app
   surfaced every error and stopped); keep them separate from generic errors. */
export class UploadValidationError extends Error {
  errors: FileError[]
  constructor(message: string, errors: FileError[]) {
    super(message)
    this.name = 'UploadValidationError'
    this.errors = errors
  }
}

async function extractError(res: Response): Promise<{ message: string; errors?: FileError[] }> {
  try {
    const body = await res.json()
    const errors = Array.isArray(body.errors) ? (body.errors as FileError[]) : undefined
    if (typeof body.detail === 'string') return { message: body.detail, errors }
    if (Array.isArray(body.detail)) {
      return {
        message: body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; '),
        errors,
      }
    }
  } catch {
    /* fall through to the generic message */
  }
  return { message: `Request failed (${res.status})` }
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const { message, errors } = await extractError(res)
    if (errors && errors.length) throw new UploadValidationError(message, errors)
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export function exportUrl(kind: 'stacked' | 'inspection', sessionId: string, wafers: string[]): string {
  const params = new URLSearchParams({ session_id: sessionId })
  for (const w of wafers) params.append('wafers', w)
  return `${BASE}/export/${kind}?${params.toString()}`
}

export const api = {
  products(): Promise<ProductsResponse> {
    return fetch(`${BASE}/products`).then((r) => parseJson<ProductsResponse>(r))
  },

  reference(product: string): Promise<Reference> {
    return fetch(`${BASE}/reference/${encodeURIComponent(product)}`).then((r) => parseJson<Reference>(r))
  },

  session(sessionId: string): Promise<InspectionsResponse> {
    return fetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}`).then((r) => parseJson<InspectionsResponse>(r))
  },

  loadExamples(): Promise<InspectionsResponse> {
    return fetch(`${BASE}/examples`, { method: 'POST' }).then((r) => parseJson<InspectionsResponse>(r))
  },

  uploadInspections(product: string, files: File[]): Promise<InspectionsResponse> {
    const form = new FormData()
    form.append('product', product)
    for (const f of files) form.append('files', f)
    return fetch(`${BASE}/inspections`, { method: 'POST', body: form }).then((r) =>
      parseJson<InspectionsResponse>(r),
    )
  },

  layouts(): Promise<LayoutsResponse> {
    return fetch(`${BASE}/layouts`).then((r) => parseJson<LayoutsResponse>(r))
  },

  previewLayout(file: File): Promise<LayoutPreview> {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE}/layouts/preview`, { method: 'POST', body: form }).then((r) => parseJson<LayoutPreview>(r))
  },

  saveLayout(request: LayoutSaveRequest): Promise<LayoutItem> {
    const form = new FormData()
    form.append('file', request.file)
    form.append('name', request.name)
    form.append('products', request.products)
    form.append('replace', String(request.replace))
    return fetch(`${BASE}/layouts`, { method: 'POST', body: form }).then((r) => parseJson<LayoutItem>(r))
  },

  deleteLayout(name: string): Promise<{ name: string; file: string; products: string[] }> {
    return fetch(`${BASE}/layouts/${encodeURIComponent(name)}`, { method: 'DELETE' }).then((r) =>
      parseJson<{ name: string; file: string; products: string[] }>(r),
    )
  },

  analyze(request: AnalyzeRequest): Promise<Analysis> {
    return fetch(`${BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }).then((r) => parseJson<Analysis>(r))
  },
}
