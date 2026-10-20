// REST client for docs/INTERFACES.md §2. Same-origin, cookie session.
import type { Widget } from '@/contracts/types'

export type Lang = 'en' | 'zh'
export type StepId = 'welcome' | 'profile' | 'site' | 'cost' | 'funding' | 'goal_plan' | 'goal_keeper'
export type StepStatus = 'done' | 'current' | 'todo' | 'stale'

export interface JourneyStep {
  id: string
  label: string
  status: StepStatus
}

/** STATE_SNAPSHOT.snapshot (INTERFACES §1). A read-only mirror of the server's journey state. */
export interface JourneyState {
  lang: Lang
  host_mode: 'embedded' | 'standalone'
  step: StepId
  steps: JourneyStep[]
  goal_id: string | null
  llm: string
  demo: boolean
  busy_widget: string | null
  /** Not in the contract yet; used as the AG-UI threadId when present. */
  journey_id?: string
}

export interface SessionUser {
  id: string
  email: string | null
  host_mode: 'embedded' | 'standalone'
  lang: Lang
}

export interface SessionResponse {
  user: SessionUser | null
  state: JourneyState | null
}

export interface DemoInfo {
  mailpit_url: string
  seed: number | string
  simulated: true
}

export interface GoalResponse {
  goal: Record<string, unknown> | null
  widgets: Widget[]
}

export interface DocumentUpload {
  doc_id: string
  filename?: string
  uploaded_at?: string
  image_url?: string
  status?: string
  lines?: { label: string; amount?: string | null; status?: string }[]
  exclusions?: string[]
}

export interface DataSource {
  id?: string
  label: string
  url?: string | null
  as_of?: string | null
  note?: string | null
  simulated?: boolean
}

export interface DocumentsResponse {
  uploads: DocumentUpload[]
  sources: DataSource[]
}

export type DemoScenario = 'none' | 'sales_dip' | 'channel_shift' | 'above_normal_draw'

/** Demo only: the mock WeBank's view of an instruction Waypoint prepared for the owner to sign. */
export interface WebankInstruction {
  id: string
  status: 'pending_signature' | 'signed'
  amount: string
  into: string
  start: string
}

export type CheckinFrequency = 'weekly' | 'fortnightly' | 'monthly'

export interface Account {
  email: string | null
  sign_in?: string
  host_mode?: 'embedded' | 'standalone'
  lang: Lang
  checkin_frequency: CheckinFrequency
  email_amounts: boolean
  consent?: { granted: boolean; granted_at?: string | null; reads?: string[] } | null
}

export interface SetasidePreview {
  chart: import('@/contracts/types').ChartSeries
  figures: Widget['figures']
  display: Widget['display']
}

/** GET {preview_url}?savings=: the compare view with the savings column at another amount. */
export interface ComparePreview {
  columns: import('@/contracts/types').CompareColumn[]
  figures: Widget['figures']
  display: Widget['display']
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`)
  }
  if (res.status === 204 || res.status === 202) {
    const text = await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
  return (await res.json()) as T
}

export const api = {
  session: () => request<SessionResponse>('api/session'),
  requestLink: (email: string, lang?: string) =>
    request<void>('api/auth/request-link', { method: 'POST', body: JSON.stringify({ email, lang }) }),
  demoSsoToken: () => request<{ token: string }>('api/demo/sso-token'),
  webankSso: (token: string, lang?: string) =>
    request<SessionResponse | void>('api/auth/webank-sso', { method: 'POST', body: JSON.stringify({ token, lang }) }),
  logout: () => request<void>('api/auth/logout', { method: 'POST' }),
  demoInfo: () => request<DemoInfo>('api/demo/info'),
  demoAdvance: (weeks: number, scenario: DemoScenario) =>
    request<unknown>('api/demo/advance', { method: 'POST', body: JSON.stringify({ weeks, scenario }) }),
  demoWebank: () => request<{ instructions: WebankInstruction[]; simulated: true }>('api/demo/webank'),
  demoWebankSign: (instructionId: string) =>
    request<{ instructions: WebankInstruction[]; simulated: true }>('api/demo/webank/sign', {
      method: 'POST',
      body: JSON.stringify({ instruction_id: instructionId }),
    }),
  /** Demo only: the sample quote photo, uploaded through the normal path so the reader reads it. */
  demoSampleQuote: async (): Promise<File> => {
    const res = await fetch('api/demo/sample-quote', { credentials: 'include' })
    if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`)
    const blob = await res.blob()
    return new File([blob], 'sample-quote.png', { type: blob.type || 'image/png' })
  },
  exportUrl: 'api/account/export',
  deleteAccount: () => request<void>('api/account', { method: 'DELETE' }),
  goal: () => request<GoalResponse>('api/goal'),
  documents: () => request<DocumentsResponse>('api/documents'),
  account: () => request<Account>('api/account'),
  patchAccount: (patch: Partial<Pick<Account, 'lang' | 'checkin_frequency' | 'email_amounts'>>) =>
    request<Account>('api/account', { method: 'PATCH', body: JSON.stringify(patch) }),
  withdrawConsent: () => request<void>('api/consent/withdraw', { method: 'POST' }),
  upload: (file: File, signal?: AbortSignal) => {
    const body = new FormData()
    body.append('file', file)
    return request<{ doc_id: string }>('api/upload', { method: 'POST', body, signal })
  },
  /** GET {preview_url}?share= (read-only, < 300 ms). */
  previewSetaside: (previewUrl: string, share: number, signal?: AbortSignal) => {
    const sep = previewUrl.includes('?') ? '&' : '?'
    return request<SetasidePreview>(`${relative(previewUrl)}${sep}share=${encodeURIComponent(share.toFixed(4))}`, {
      signal,
    })
  },
  /** GET {preview_url}?savings= (read-only): every compare column, the savings one at this amount. */
  previewCompare: (previewUrl: string, savings: string, signal?: AbortSignal) => {
    const sep = previewUrl.includes('?') ? '&' : '?'
    return request<ComparePreview>(`${relative(previewUrl)}${sep}savings=${encodeURIComponent(savings)}`, { signal })
  },
  docImageUrl: (docId: string) => `api/docs/${encodeURIComponent(docId)}/image`,
}

/**
 * Server paths are absolute ("/api/..."). The app may be served behind a path prefix,
 * so same-origin paths are made relative to the document base.
 */
export function relative(url: string): string {
  return url.startsWith('/') && !url.startsWith('//') ? url.slice(1) : url
}
