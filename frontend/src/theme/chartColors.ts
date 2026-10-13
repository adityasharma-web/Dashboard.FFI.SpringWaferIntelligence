import { useEffect, useState } from 'react'
import type { Theme } from './useTheme'

/* Plotly receives concrete color strings (it cannot resolve CSS var() inside
   figure JSON), so chart figures read the design tokens at runtime, with
   theme-matched fallbacks for test environments without stylesheets.

   The five spring STATUS colors are deliberately NOT theme tokens: they are
   the domain palette from the reference app (Good / Low / Med / Killer /
   Uninspected) and come from the API payload so both renderers agree. */

export interface ChartColors {
  text: string
  text2: string
  text3: string
  border: string
  borderMuted: string
  surface: string
  inset: string
  bg: string
  good: string
  warn: string
  bad: string
  accent: string
  accentFg: string
  waferFill: string
  waferEdge: string
  gangOutline: string
  gangLabel: string
}

const FALLBACKS: Record<Theme, ChartColors> = {
  dark: {
    text: '#ffffff',
    text2: '#b8b8b8',
    text3: '#8a8a8a',
    border: '#262626',
    borderMuted: '#1a1a1a',
    surface: '#0a0a0a',
    inset: '#101010',
    bg: '#000000',
    good: '#3fb950',
    warn: '#d29922',
    bad: '#f85149',
    accent: '#2f81f7',
    accentFg: '#58a6ff',
    waferFill: '#0d0d0d',
    waferEdge: '#4d4d4d',
    gangOutline: '#5a6b7c',
    gangLabel: '#8a98a8',
  },
  light: {
    text: '#1f2328',
    text2: '#59636e',
    text3: '#818b98',
    border: '#d0d7de',
    borderMuted: '#e6eaee',
    surface: '#ffffff',
    inset: '#f6f8fa',
    bg: '#ffffff',
    good: '#1a7f37',
    warn: '#9a6700',
    bad: '#cf222e',
    accent: '#0969da',
    accentFg: '#0969da',
    waferFill: '#f6f8fa',
    waferEdge: '#afb8c1',
    gangOutline: '#6e7d8c',
    gangLabel: '#52647a',
  },
}

const TOKENS: Record<keyof ChartColors, string> = {
  text: '--text',
  text2: '--text-2',
  text3: '--text-3',
  border: '--border',
  borderMuted: '--border-muted',
  surface: '--surface',
  inset: '--inset',
  bg: '--bg',
  good: '--good',
  warn: '--warn',
  bad: '--bad',
  accent: '--accent',
  accentFg: '--accent-fg',
  waferFill: '--wafer-fill',
  waferEdge: '--wafer-edge',
  gangOutline: '--gang-outline',
  gangLabel: '--gang-label',
}

export function resolveChartColors(theme: Theme): ChartColors {
  const styles = getComputedStyle(document.documentElement)
  const out = { ...FALLBACKS[theme] }
  for (const key of Object.keys(TOKENS) as (keyof ChartColors)[]) {
    const v = styles.getPropertyValue(TOKENS[key]).trim()
    if (v) out[key] = v
  }
  return out
}

export function useChartColors(theme: Theme): ChartColors {
  const [colors, setColors] = useState<ChartColors>(() => FALLBACKS[theme])
  useEffect(() => {
    // Read after useTheme's effect has stamped data-theme on <html>.
    setColors(resolveChartColors(theme))
  }, [theme])
  return colors
}

/* Hex -> rgba() for translucent fills derived from opaque design tokens. */
export function rgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r},${g},${b},${alpha})`
}
