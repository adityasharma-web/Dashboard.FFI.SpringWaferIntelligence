/* Mirrors of the FastAPI response models (backend/app.py). The frontend is a
   pure rendering client: every number on screen comes from these payloads. */

/* Severity statuses (CSV/XLSX uploads). CloudPCS XML sessions use the
   defect-code model instead: 'Good' | <DEFECT_CODE…> | 'Uninspected', so the
   status list and palette always come from the analysis payload. */
export type SpringState = 'Good' | 'Low' | 'Med' | 'Killer' | 'Uninspected'
export type StatusModel = 'severity' | 'defect_code'

export interface ProductsResponse {
  products: string[]
  examples_product: string
  examples_available: boolean
}

export interface GangBounds {
  die: number
  xmin: number
  xmax: number
  ymin: number
  ymax: number
}

/* 'spring': every spring of every gang (4 mm segments). 'die': one row per
   die, drawn as cells at the grid pitch; the engine treats each die as a gang
   with a single spring, so every analysis is shared. */
export type LayoutKind = 'spring' | 'die'

export interface Pitch {
  x: number
  y: number
}

export interface Reference {
  product: string
  kind: LayoutKind
  pitch: Pitch | null
  spring_count: number
  gang_count: number
  center: { x: number; y: number }
  die: number[]
  spring: number[]
  x: number[]
  y: number[]
  gangs: GangBounds[]
  caveat: string
}

export interface FileSummary {
  filename: string
  wafer_id: string
  observations: number
}

export interface InspectionsResponse {
  session_id: string
  product: string
  source: 'upload' | 'synthetic_examples'
  status_model: StatusModel
  wafers: string[]
  files: FileSummary[]
  synthetic: boolean
}

export interface FileError {
  filename: string
  error: string
}

export interface HeaderMetrics {
  wafers: number
  springs_in_reference: number
  observations: number
  bad: number
  defect_rate: number | null
}

export interface StatusCount {
  status: string
  count: number
}

export interface IndividualWafer {
  wafer_id: string
  status_codes: number[]
  counts: StatusCount[]
  uninspected: number
}

export interface StackedMetrics {
  die: number[]
  spring: number[]
  inspected: number[]
  defects: number[]
  killer: number[]
  defect_rate: (number | null)[]
  uninspected_springs: number
}

export interface Peak {
  X_mm: number
  Y_mm: number
  Local_defect_rate: number
  Excess_vs_global: number
}

export interface RecurrenceRow {
  die: number
  spring: number
  inspected: number
  defects: number
  q: number
  p: number | null
}

export interface SpatialResult {
  bin_edges: number[]
  bin_centers: number[]
  rate_grid: (number | null)[][]
  baseline: number
  peaks: Peak[]
  recurrence: RecurrenceRow[]
  recurrence_total_rows: number
  recurrence_min_inspected: number
  recurrence_tested: boolean
}

export interface ZoneRow {
  zone: string
  inspected: number
  defects: number
  defect_rate: number
}

export interface SectorRow {
  sector: string
  defect_rate: number | null
  size: number
}

export interface SignatureResult {
  zones: ZoneRow[]
  sectors: SectorRow[]
  messages: string[]
}

export interface GangRow {
  wafer_id: string
  die: number
  inspected: number
  bad: number
  total_springs: number
  bad_pct: number
  complete: boolean
  disposition: 'PASS' | 'SCRAP' | 'INCOMPLETE'
}

export interface GangYieldResult {
  rows: GangRow[]
  scrapped: number
  total: number
  threshold: number
  rule: string
}

export interface Analysis {
  session_id: string
  product: string
  source: 'upload' | 'synthetic_examples'
  synthetic: boolean
  status_model: StatusModel
  wafers: string[]
  bandwidth: number
  states: string[]
  colors: Record<string, string>
  status_counts: StatusCount[]
  header: HeaderMetrics
  individual: IndividualWafer[]
  stacked: StackedMetrics
  spatial: SpatialResult
  signature: SignatureResult
  gang_yield: GangYieldResult
  caveats: Record<string, string>
}

export interface LayoutSummary {
  springs: number
  gangs: number
  springs_per_gang_min: number
  springs_per_gang_max: number
  center_x: number
  center_y: number
  x_min: number
  x_max: number
  y_min: number
  y_max: number
  max_radius_mm: number
  kind: LayoutKind
  units: 'mm' | 'um->mm'
  pitch_x_mm: number | null
  pitch_y_mm: number | null
  warnings: string[]
}

export interface LayoutItem {
  name: string
  file: string
  products: string[]
  implicit: boolean
  saved_at: string | null
  source_filename: string | null
  size_bytes: number
  summary: LayoutSummary | null
  error: string | null
}

export interface LayoutsResponse {
  layouts: LayoutItem[]
}

/* The preview carries the same geometry fields as Reference so the wafer
   figure builders can draw it unchanged. */
export interface LayoutPreview {
  filename: string
  suggested_name: string
  summary: LayoutSummary
  kind: LayoutKind
  pitch: Pitch | null
  die: number[]
  spring: number[]
  x: number[]
  y: number[]
  gangs: GangBounds[]
  caveat: string
}

export interface LayoutSaveRequest {
  name: string
  products: string
  replace: boolean
  file: File
}

export interface AnalyzeRequest {
  session_id: string
  wafers: string[] | null
  bandwidth: number
}
