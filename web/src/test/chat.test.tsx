import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FRONTEND_TOOLS } from '@/chat/chatContext'
import { ChatProvider } from '@/chat/ChatProvider'
import { ChatTab } from '@/chat/ChatTab'
import { fixtures } from '@/dev/fixtures'
import type { JourneyState } from '@/lib/api'
import { widgetRenderers } from '@/widgets/registry'

const state: JourneyState = {
  lang: 'en',
  host_mode: 'standalone',
  step: 'site',
  steps: [
    { id: 'profile', label: 'Your business', status: 'done' },
    { id: 'site', label: 'Where', status: 'current' },
    { id: 'cost', label: 'What it costs', status: 'todo' },
    { id: 'funding', label: 'How to pay', status: 'todo' },
    { id: 'goal_plan', label: 'Your plan', status: 'todo' },
  ],
  goal_id: null,
  llm: 'off',
  demo: true,
  busy_widget: null,
}

const quickReplies = fixtures.find((f) => f.name === 'quick_replies')!.widget

function sse(events: object[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
}

interface RunBody {
  threadId: string
  runId: string
  tools: unknown[]
  context: unknown[]
  messages: { role: string; content?: string }[]
  forwardedProps: Record<string, unknown>
}

/** A fake AG-UI endpoint: the first run replies with a message and a quick_replies widget. */
function mockAgui() {
  const bodies: RunBody[] = []
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as RunBody
    bodies.push(body)
    const first = bodies.length === 1
    const events = [
      { type: 'RUN_STARTED', threadId: body.threadId, runId: body.runId },
      { type: 'STATE_SNAPSHOT', snapshot: state },
      ...(first
        ? [
            { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' },
            { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'What matters most for your first shop?' },
            { type: 'TEXT_MESSAGE_END', messageId: 'm1' },
            { type: 'TOOL_CALL_START', toolCallId: quickReplies.id, toolCallName: 'quick_replies', parentMessageId: 'm1' },
            { type: 'TOOL_CALL_ARGS', toolCallId: quickReplies.id, delta: JSON.stringify(quickReplies) },
            { type: 'TOOL_CALL_END', toolCallId: quickReplies.id },
          ]
        : [
            { type: 'TEXT_MESSAGE_START', messageId: `m${bodies.length}`, role: 'assistant' },
            { type: 'TEXT_MESSAGE_CONTENT', messageId: `m${bodies.length}`, delta: 'Got it.' },
            { type: 'TEXT_MESSAGE_END', messageId: `m${bodies.length}` },
          ]),
      { type: 'RUN_FINISHED', threadId: body.threadId, runId: body.runId },
    ]
    return new Response(sse(events), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, bodies }
}

afterEach(() => vi.unstubAllGlobals())

describe('chat over AG-UI', () => {
  it('resumes on mount, renders bot text, the progress strip and the widget', async () => {
    const { fetchMock, bodies } = mockAgui()
    render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    expect(await screen.findByText('What matters most for your first shop?')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Near my kind of customer/ })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Your progress' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]![0]).toBe('api/agui')
    expect(fetchMock.mock.calls[0]![1]).toMatchObject({ method: 'POST', credentials: 'include' })
    expect(bodies[0]!.threadId).toBe('j_1')
    expect(bodies[0]!.forwardedProps).toEqual({})
  })

  it('a widget tap sends a WidgetEvent in forwardedProps plus a short user message', async () => {
    const { bodies } = mockAgui()
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    await user.click(await screen.findByRole('button', { name: /Low rent/ }))
    await waitFor(() => expect(bodies).toHaveLength(2))
    const run = bodies[1]!
    expect(run.forwardedProps).toEqual({
      widget_event: { widget_id: 'w_qr1', event: 'reply', value: 'low_rent', data: { slot: 'priority' } },
    })
    expect(run.messages.at(-1)).toMatchObject({ role: 'user', content: 'Low rent' })
    expect(await screen.findByText('Got it.')).toBeInTheDocument()
    // The answered quick replies are now history.
    await waitFor(() => expect(screen.getByRole('button', { name: /Foot traffic/ })).toBeDisabled())
  })

  it('free text is sent as the last user message, with no widget_event', async () => {
    const { bodies } = mockAgui()
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    await screen.findByText('What matters most for your first shop?')
    await user.type(screen.getByLabelText('Message Waypoint'), 'Somewhere near students{Enter}')
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1]!.forwardedProps).toEqual({})
    expect(bodies[1]!.messages.at(-1)).toMatchObject({ role: 'user', content: 'Somewhere near students' })
  })

  it('tapping a done step sends reopen_step', async () => {
    const { bodies } = mockAgui()
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    await user.click(await screen.findByRole('button', { name: 'Go back to Your business' }))
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1]!.forwardedProps.widget_event).toMatchObject({ event: 'reopen_step', value: 'profile' })
  })

  it('shows an error with retry when the run fails', async () => {
    let n = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        n += 1
        return new Response('boom', { status: 500 })
      }),
    )
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    expect(await screen.findByText(/Something went wrong/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(n).toBe(2))
  })

  it('says plainly to wait when the server rate-limits the chat (429)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ detail: 'Too many messages in a short time.' }, { status: 429 })),
    )
    render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    expect(await screen.findByText(/a lot of messages in a short time\. Wait a minute/)).toBeInTheDocument()
    expect(screen.queryByText(/Something went wrong/)).not.toBeInTheDocument()
  })
})

describe('two-phase turns (waypoint.text_slot)', () => {
  it('reserves each message in place, fills it later, and drops a slot that never gets words', async () => {
    const units = fixtures.find((f) => f.name === 'unit_compare')!.widget
    const cost = fixtures.find((f) => f.name === 'cost_breakdown')!.widget
    const call = (w: typeof units, parent: string) => [
      { type: 'TOOL_CALL_START', toolCallId: w.id, toolCallName: w.payload.type, parentMessageId: parent },
      { type: 'TOOL_CALL_ARGS', toolCallId: w.id, delta: JSON.stringify(w) },
      { type: 'TOOL_CALL_END', toolCallId: w.id },
    ]
    const text = (id: string, delta: string) => [
      { type: 'TEXT_MESSAGE_START', messageId: id, role: 'assistant' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: id, delta },
      { type: 'TEXT_MESSAGE_END', messageId: id },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_u: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body)) as RunBody
        const events = [
          { type: 'RUN_STARTED', threadId: body.threadId, runId: body.runId },
          { type: 'CUSTOM', name: 'waypoint.text_slot', value: { id: 's1' } },
          ...call(units, 'p1'),
          { type: 'CUSTOM', name: 'waypoint.text_slot', value: { id: 's2' } },
          ...call(cost, 'p2'),
          { type: 'CUSTOM', name: 'waypoint.text_slot', value: { id: 's3' } },
          // Words arrive after all the cards, out of order.
          ...text('s2', 'And here is what it costs.'),
          ...text('s1', 'Here are three units.'),
          { type: 'CUSTOM', name: 'waypoint.notice', value: { code: 'compose_failed', retry: true } },
          { type: 'RUN_FINISHED', threadId: body.threadId, runId: body.runId },
        ]
        return new Response(sse(events), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      }),
    )
    const { container } = render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    const first = await screen.findByText('Here are three units.')
    const second = screen.getByText('And here is what it costs.')
    const unitsCard = screen.getByRole('group', { name: 'Units to compare' })
    const costCard = screen.getByRole('group', { name: 'What it costs to open' })
    const order = (a: Element, b: Element) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING
    expect(order(first, unitsCard)).toBeTruthy()
    expect(order(unitsCard, second)).toBeTruthy()
    expect(order(second, costCard)).toBeTruthy()
    // The unfilled slot is gone once the run finished; the notice explains.
    await waitFor(() => expect(container.querySelector('#msg-s3')).toBeNull())
    expect(screen.getByText(/couldn't put that into words/)).toBeInTheDocument()
    expect(screen.queryByText('Waypoint is typing')).toBeNull()
  })
})

describe('server-side enforcement (SPEC §2.2)', () => {
  it('every run declares no frontend tools and no context', async () => {
    const { bodies } = mockAgui()
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="j_1">
        <ChatTab />
      </ChatProvider>,
    )
    await user.click(await screen.findByRole('button', { name: /Low rent/ }))
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(FRONTEND_TOOLS).toEqual([])
    for (const b of bodies) {
      expect(b.tools).toEqual([])
      expect(b.context).toEqual([])
    }
  })

  it('the widget registry holds display-only renderers (no handlers, no human-in-the-loop)', () => {
    for (const r of widgetRenderers) {
      expect(Object.keys(r).sort()).toEqual(['name', 'render'])
      expect(r).not.toHaveProperty('handler')
      expect(r).not.toHaveProperty('parameters')
      expect(Object.isFrozen(r)).toBe(true)
    }
    expect(Object.isFrozen(widgetRenderers)).toBe(true)
  })

  it('the app does not depend on CopilotKit frontend-tool APIs', async () => {
    const sources = import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true })
    for (const [path, src] of Object.entries(sources)) {
      if (path.includes('/test/')) continue
      expect(src as string, path).not.toMatch(/useFrontendTool|useHumanInTheLoop|useCopilotAction|frontendTools\s*=|humanInTheLoop\s*=/)
    }
  })
})
