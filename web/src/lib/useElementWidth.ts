import { useCallback, useState } from 'react'

/** A callback ref plus the element's current width in px (`fallback` until measured). */
export function useElementWidth<T extends HTMLElement>(fallback: number): [(el: T | null) => void | (() => void), number] {
  const [width, setWidth] = useState(fallback)
  const ref = useCallback((el: T | null) => {
    if (!el) return
    const measure = () => {
      const w = el.getBoundingClientRect().width
      if (w > 0) setWidth(Math.round(w))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}
