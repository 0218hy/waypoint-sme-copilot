import { createContext, useContext } from 'react'
import { api, relative, type ComparePreview, type SetasidePreview } from '@/lib/api'

/** App-level services widgets may use. The gallery swaps these for fixtures. */
export interface WidgetEnv {
  /** Maps a server URL (GeoJSON, document image) to the URL to load. */
  resolveUrl: (url: string) => string
  previewSetaside: (previewUrl: string, share: number, signal: AbortSignal) => Promise<SetasidePreview>
  previewCompare: (previewUrl: string, savings: string, signal: AbortSignal) => Promise<ComparePreview>
  upload: (file: File, signal?: AbortSignal) => Promise<{ doc_id: string }>
  /** Switch the app's tab (plan_summary "Change in chat", status_card "Open the Goal tab"). */
  openTab?: (tab: 'chat' | 'goal') => void
  /** Demo only: fetches the sample quote photo (then uploaded through the normal path). */
  sampleQuote?: () => Promise<File>
}

export const defaultWidgetEnv: WidgetEnv = {
  resolveUrl: relative,
  previewSetaside: (u, s, signal) => api.previewSetaside(u, s, signal),
  previewCompare: (u, s, signal) => api.previewCompare(u, s, signal),
  upload: (f, signal) => api.upload(f, signal),
}

export const WidgetEnvContext = createContext<WidgetEnv>(defaultWidgetEnv)

export function useWidgetEnv(): WidgetEnv {
  return useContext(WidgetEnvContext)
}
