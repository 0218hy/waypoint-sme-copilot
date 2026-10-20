import { useEffect, useState } from 'react'

export interface ChartTheme {
  text: string
  muted: string
  faint: string
  grid: string
  surface: string
  border: string
  accent: string
  band: string
  series: string[]
  danger: string
  warning: string
  success: string
}

function read(): ChartTheme {
  const cs = typeof window === 'undefined' ? null : getComputedStyle(document.documentElement)
  const v = (name: string, fallback: string) => cs?.getPropertyValue(name).trim() || fallback
  return {
    text: v('--text', '#17202b'),
    muted: v('--text-muted', '#566273'),
    faint: v('--text-faint', '#7d8796'),
    grid: v('--chart-grid', '#e5e8ec'),
    surface: v('--surface', '#ffffff'),
    border: v('--border', '#dde1e7'),
    accent: v('--accent', '#0f766e'),
    band: v('--chart-band', 'rgba(15,118,110,0.18)'),
    series: [1, 2, 3, 4, 5, 6].map((i) => v(`--chart-${i}`, '#888')),
    danger: v('--danger', '#b42318'),
    warning: v('--warning', '#b45309'),
    success: v('--success', '#15803d'),
  }
}

/** Chart colours from the CSS tokens; re-read when the theme changes. */
export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState(read)
  useEffect(() => {
    const update = () => setTheme(read())
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    mq?.addEventListener?.('change', update)
    const mo = new MutationObserver(update)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      mq?.removeEventListener?.('change', update)
      mo.disconnect()
    }
  }, [])
  return theme
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const update = () => setReduced(mq.matches)
    mq.addEventListener?.('change', update)
    return () => mq.removeEventListener?.('change', update)
  }, [])
  return reduced
}

/** Compact axis labels: the UI formats axis labels only (INTERFACES §3). */
export function compactAxis(value: number, lang: string): string {
  return new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-SG', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

/** Currency for chart tooltips and table fallbacks of server series. */
export function money(value: number, currency: string, lang: string): string {
  return new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-SG', {
    style: 'currency',
    currency,
    currencyDisplay: currency === 'CNY' && lang !== 'zh' ? 'code' : 'narrowSymbol',
    maximumFractionDigits: 0,
  }).format(value)
}
