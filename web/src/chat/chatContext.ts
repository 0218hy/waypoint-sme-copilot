import { HttpAgent } from '@ag-ui/client'
import type { Message } from '@ag-ui/client'
import { createContext, useContext } from 'react'
import type { WidgetEvent } from '@/contracts/types'
import type { JourneyState } from '@/lib/api'

/**
 * Waypoint registers NO frontend tools and NO human-in-the-loop tools (SPEC §2.2). Every run
 * sends this empty list; widgets only render and report WidgetEvents in forwardedProps.
 */
export const FRONTEND_TOOLS: readonly never[] = Object.freeze([])

export const AGUI_URL = 'api/agui'

/** `error` when the server answered 429 (too many runs in a short time; app/security.py). */
export const RATE_LIMITED = 'rate_limited'

export function createAgent(threadId: string): HttpAgent {
  return new HttpAgent({
    url: AGUI_URL,
    threadId,
    // Same-origin session cookie identifies the owner.
    fetch: (url, init) => fetch(url, { ...init, credentials: 'include' }),
  })
}

/** AG-UI CUSTOM `waypoint.notice`: the model couldn't write this turn's message (cards are current). */
export interface ChatNotice {
  code: 'compose_failed' | 'model_unavailable' | string
  retry: boolean
}

export interface ChatValue {
  messages: Message[]
  /** The latest `waypoint.notice`, cleared when the next run starts. */
  notice: ChatNotice | null
  /** Message ids reserved by `waypoint.text_slot` whose words haven't arrived yet. */
  slots: ReadonlySet<string>
  /** The latest `waypoint.thinking` stage while a run is active. */
  thinking: string | null
  /** Asks the server to write the last turn's message again (no user message). */
  retryCompose: () => void
  journey: JourneyState | null
  running: boolean
  error: string | null
  /** Sends free text (the last `user` message). */
  sendText: (text: string) => void
  /** Sends a structured widget event plus a short transcript line (INTERFACES §1). */
  sendEvent: (event: WidgetEvent, label: string) => void
  /** Re-runs the last request after an error. */
  retry: () => void
}

export const ChatContext = createContext<ChatValue | null>(null)

export function useChat(): ChatValue {
  const v = useContext(ChatContext)
  if (!v) throw new Error('useChat outside ChatProvider')
  return v
}

export function useOptionalChat(): ChatValue | null {
  return useContext(ChatContext)
}

