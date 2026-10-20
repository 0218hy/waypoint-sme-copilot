import { useSyncExternalStore } from 'react'

/** True while the media query matches (e.g. the lg / xl desktop breakpoints). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia?.(query)
      mq?.addEventListener?.('change', cb)
      return () => mq?.removeEventListener?.('change', cb)
    },
    () => !!window.matchMedia?.(query).matches,
    () => false,
  )
}

export const LG = '(min-width: 1024px)'
export const XL = '(min-width: 1280px)'
