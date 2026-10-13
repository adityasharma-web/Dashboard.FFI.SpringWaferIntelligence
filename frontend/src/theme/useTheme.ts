import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

function initialTheme(): Theme {
  const requested = new URLSearchParams(window.location.search).get('theme')
  if (requested === 'light' || requested === 'dark') return requested
  const stored = localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  return {
    theme,
    toggle: () => setTheme((t) => (t === 'light' ? 'dark' : 'light')),
  }
}
