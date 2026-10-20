import { useCallback, useEffect, useState } from 'react'
import type { LoadState } from './useJson'

/** Load on mount (and when deps change), with reload and local replace. */
export function useApi<T>(load: () => Promise<T>, deps: readonly unknown[] = []): [LoadState<T>, () => void, (d: T) => void] {
  const [n, setN] = useState(0)
  const [result, setResult] = useState<{ n: number; key: string; state: LoadState<T> } | null>(null)
  const key = JSON.stringify(deps)
  useEffect(() => {
    let alive = true
    load().then(
      (data) => alive && setResult({ n, key, state: { status: 'ready', data } }),
      (e: unknown) => alive && setResult({ n, key, state: { status: 'error', error: e instanceof Error ? e.message : String(e) } }),
    )
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, key])
  const reload = useCallback(() => setN((x) => x + 1), [])
  const set = useCallback((data: T) => setResult((r) => (r ? { ...r, state: { status: 'ready', data } } : r)), [])
  const state: LoadState<T> = result && result.n === n && result.key === key ? result.state : { status: 'loading' }
  return [state, reload, set]
}
