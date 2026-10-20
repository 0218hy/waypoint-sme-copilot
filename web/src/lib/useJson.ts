import { useCallback, useEffect, useState } from 'react'

export type LoadState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: string }
  | { status: 'ready'; data: T }

const cache = new Map<string, Promise<unknown>>()

/** Fetch JSON once per URL (cached), with loading / error / retry. */
export function useJson<T>(url: string | null): [LoadState<T>, () => void] {
  const [state, setState] = useState<LoadState<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!url) return
    let alive = true
    let p = cache.get(url)
    if (!p) {
      p = fetch(url, { credentials: 'include' }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      cache.set(url, p)
      p.catch(() => cache.delete(url))
    }
    p.then(
      (data) => alive && setState({ status: 'ready', data: data as T }),
      (e: unknown) => alive && setState({ status: 'error', error: e instanceof Error ? e.message : String(e) }),
    )
    return () => {
      alive = false
    }
  }, [url, attempt])
  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((a) => a + 1)
  }, [])
  return [state, retry]
}
