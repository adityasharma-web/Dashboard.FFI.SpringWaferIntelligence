/* Formatting helpers. The reference app used Streamlit's `{:,}` and `{:.1%}`
   formats; these reproduce those digit for digit. */

export function fmt(value: unknown, digits = 0, fallback = '—'): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return fallback
  }
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/* Fraction (0..1) -> percentage string, e.g. 0.12783 -> "12.8%". */
export function pct(value: unknown, digits = 1, fallback = 'N/A'): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return fallback
  return `${fmt(Number(value) * 100, digits)}%`
}

/* Small probabilities (p / q values) in a compact scientific form. */
export function sci(value: unknown, fallback = '—'): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return fallback
  const v = Number(value)
  if (v === 0) return '0'
  if (v >= 0.001) return v.toFixed(4)
  return v.toExponential(2)
}
