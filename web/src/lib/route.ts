import { useEffect, useState } from 'react'

export type Tab = 'chat' | 'goal' | 'documents' | 'account'
export const TABS: readonly Tab[] = ['chat', 'goal', 'documents', 'account']

function read(): string {
  const h = window.location.hash.replace(/^#/, '')
  return h.startsWith('/') ? h : `/${h}`
}

/** Hash routes keep the app servable from any path prefix (and inside a WebView). */
export function useHashRoute(): [string, (path: string) => void] {
  const [path, setPath] = useState(read)
  useEffect(() => {
    const on = () => setPath(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const go = (p: string) => {
    if (read() !== p) window.location.hash = p
  }
  return [path, go]
}

export function tabFromPath(path: string): Tab {
  const seg = path.split('/')[1] as Tab
  return TABS.includes(seg) ? seg : 'chat'
}
