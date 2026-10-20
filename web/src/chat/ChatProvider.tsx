import { randomUUID, type HttpAgent, type Message } from '@ag-ui/client'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { WidgetEvent } from '@/contracts/types'
import type { JourneyState } from '@/lib/api'
import { takeEmailLink, type EmailLink } from '@/lib/emailLink'
import i18n from '@/i18n'
import { ChatContext, createAgent, FRONTEND_TOOLS, RATE_LIMITED, type ChatNotice, type ChatValue } from './chatContext'

interface RunRequest {
  forwardedProps: Record<string, unknown>
}

interface ChatProviderProps {
  threadId: string
  initialState?: JourneyState | null
  children: ReactNode
  /** Called when the server says the session is gone (HTTP 401). */
  onUnauthorized?: () => void
  /** Injected in tests. */
  agent?: HttpAgent
  /** Send an empty run on mount so the server replies with MESSAGES_SNAPSHOT (default true). */
  resume?: boolean
  /** The email link to open with that first run, once (default: the one read from the address bar). */
  takeLink?: () => EmailLink | null
}

export function ChatProvider({
  threadId,
  initialState = null,
  children,
  onUnauthorized,
  agent: injected,
  resume = true,
  takeLink = takeEmailLink,
}: ChatProviderProps) {
  const agent = useMemo(() => injected ?? createAgent(threadId), [injected, threadId])
  const [messages, setMessages] = useState<Message[]>(() => [...agent.messages])
  const [journey, setJourney] = useState<JourneyState | null>(initialState)
  const [running, setRunning] = useState(false)
  // Exposed on <html> for end-to-end drivers (demo/record.py): whether an agent run is streaming.
  useEffect(() => {
    document.documentElement.dataset.agentRunning = running ? 'true' : 'false'
  }, [running])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<ChatNotice | null>(null)
  const [thinking, setThinking] = useState<string | null>(null)
  const [slots, setSlots] = useState<ReadonlySet<string>>(() => new Set())
  const slotsRef = useRef(new Set<string>())
  const lastRequest = useRef<RunRequest | null>(null)
  const queue = useRef<Promise<void>>(Promise.resolve())
  const unauthorizedRef = useRef(onUnauthorized)
  useEffect(() => {
    unauthorizedRef.current = onUnauthorized
  }, [onUnauthorized])

  useEffect(() => {
    const sub = agent.subscribe({
      onMessagesChanged: ({ messages: m }) => setMessages([...m]),
      onStateChanged: ({ state }) => {
        const next = state as JourneyState
        setJourney(next)
        // The owner may pick a language in the chat; the interface follows it.
        if (next?.lang && !i18n.language.startsWith(next.lang)) void i18n.changeLanguage(next.lang)
      },
      onRunErrorEvent: ({ event }) => setError(event.message || 'error'),
      onTextMessageEndEvent: ({ event }) => {
        if (slotsRef.current.delete(event.messageId)) setSlots(new Set(slotsRef.current))
      },
      // A slot that never got its words is removed (a waypoint.notice explains why).
      onRunFinishedEvent: ({ messages: current }) => {
        const unfilled = dropUnfilled(current, slotsRef.current)
        return unfilled ? { messages: unfilled } : undefined
      },
      onCustomEvent: ({ event, messages: current }) => {
        const value = (event.value ?? {}) as Record<string, unknown>
        if (event.name === 'waypoint.text_slot' && typeof value.id === 'string') {
          // Two-phase turns: reserve the message's place now (cards follow at once); the
          // TEXT_MESSAGE_* events with this id fill it in place a few seconds later.
          const id = value.id
          slotsRef.current.add(id)
          setSlots(new Set(slotsRef.current))
          if (current.some((m) => m.id === id)) return
          return { messages: [...current, { id, role: 'assistant', content: '' }] }
        }
        if (event.name === 'waypoint.notice') {
          setNotice({ code: String(value.code ?? 'compose_failed'), retry: value.retry !== false })
        } else if (event.name === 'waypoint.thinking') {
          setThinking(typeof value.stage === 'string' ? value.stage : 'thinking')
        }
      },
    })
    return () => sub.unsubscribe()
  }, [agent])

  const run = useCallback(
    (req: RunRequest) => {
      lastRequest.current = req
      // Runs are serialised: one at a time, in order.
      queue.current = queue.current.then(async () => {
        setRunning(true)
        setError(null)
        setNotice(null)
        setThinking(null)
        try {
          await agent.runAgent({
            runId: randomUUID(),
            tools: [...FRONTEND_TOOLS],
            context: [],
            forwardedProps: req.forwardedProps,
          })
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e)
          if (/\b401\b/.test(msg)) unauthorizedRef.current?.()
          setError(/\b429\b/.test(msg) ? RATE_LIMITED : msg || 'error')
        } finally {
          const unfilled = dropUnfilled(agent.messages, slotsRef.current)
          if (unfilled) agent.setMessages(unfilled)
          slotsRef.current.clear()
          setSlots(new Set())
          setRunning(false)
          setThinking(null)
        }
      })
    },
    [agent],
  )

  const resumed = useRef(false)
  useEffect(() => {
    if (!resume || resumed.current) return
    resumed.current = true
    // An email's link (?checkin= / ?alert=) rides on the opening run; the server checks it.
    const link = takeLink()
    run({ forwardedProps: link ? { email_link: link } : {} })
  }, [resume, run, takeLink])

  const sendText = useCallback(
    (text: string) => {
      const content = text.trim()
      if (!content) return
      agent.addMessage({ id: randomUUID(), role: 'user', content })
      run({ forwardedProps: {} })
    },
    [agent, run],
  )

  const sendEvent = useCallback(
    (event: WidgetEvent, label: string) => {
      agent.addMessage({ id: randomUUID(), role: 'user', content: label })
      run({ forwardedProps: { widget_event: { value: null, data: {}, ...event } } })
    },
    [agent, run],
  )

  const retryCompose = useCallback(() => {
    run({ forwardedProps: { retry_compose: true } })
  }, [run])

  const retry = useCallback(() => {
    run(lastRequest.current ?? { forwardedProps: {} })
  }, [run])

  const value = useMemo<ChatValue>(
    () => ({ messages, journey, running, error, notice, thinking, slots, sendText, sendEvent, retry, retryCompose }),
    [messages, journey, running, error, notice, thinking, slots, sendText, sendEvent, retry, retryCompose],
  )
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

/** Messages without the reserved slots that are still empty, or null when there are none. */
function dropUnfilled(messages: readonly Message[], slots: ReadonlySet<string>): Message[] | null {
  const keep: Message[] = messages.filter((m) => !(slots.has(m.id) && m.role === 'assistant' && !m.content && !(m.toolCalls?.length ?? 0)))
  return keep.length === messages.length ? null : keep
}
