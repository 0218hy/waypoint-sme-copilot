import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatProvider } from '@/chat/ChatProvider'
import { ChatTab } from '@/chat/ChatTab'
import { DemoControls } from '@/components/DemoControls'
import { fixtures } from '@/dev/fixtures'
import type { JourneyState } from '@/lib/api'

const fx = (name: string) => structuredClone(fixtures.find((f) => f.name === name)!.widget)

const state: JourneyState = {
  lang: 'en',
  host_mode: 'standalone',
  step: 'cost',
  steps: [
    { id: 'profile', label: 'Your business', status: 'done' },
    { id: 'site', label: 'Where', status: 'done' },
    { id: 'cost', label: 'What it costs', status: 'current' },
    { id: 'funding', label: 'How to pay', status: 'todo' },
    { id: 'goal_plan', label: 'Your plan', status: 'todo' },
  ],
  goal_id: null,
  llm: 'test',
  demo: true,
  busy_widget: null,
}

interface Body {
  threadId: string
  runId: string
  messages: unknown[]
  forwardedProps: Record<string, unknown>
}

function sse(events: object[]) {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
}

function toolCall(w: ReturnType<typeof fx>, parent: string) {
  return [
    { type: 'TOOL_CALL_START', toolCallId: w.id, toolCallName: w.payload.type, parentMessageId: parent },
    { type: 'TOOL_CALL_ARGS', toolCallId: w.id, delta: JSON.stringify(w) },
    { type: 'TOOL_CALL_END', toolCallId: w.id },
  ]
}

/** First run: two hero widgets (units, then costs). Later runs: the server can't word the turn. */
function mockServer() {
  const bodies: Body[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (!String(url).includes('agui')) return new Response('{}', { status: 404 })
      const body = JSON.parse(String(init?.body)) as Body
      bodies.push(body)
      const head = [
        { type: 'RUN_STARTED', threadId: body.threadId, runId: body.runId },
        { type: 'STATE_SNAPSHOT', snapshot: state },
      ]
      const tail = [{ type: 'RUN_FINISHED', threadId: body.threadId, runId: body.runId }]
      const events =
        bodies.length === 1
          ? [
              ...head,
              { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' },
              { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'Here are units.' },
              { type: 'TEXT_MESSAGE_END', messageId: 'm1' },
              ...toolCall(fx('unit_compare'), 'm1'),
              { type: 'TEXT_MESSAGE_START', messageId: 'm2', role: 'assistant' },
              { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: 'And what it costs.' },
              { type: 'TEXT_MESSAGE_END', messageId: 'm2' },
              ...toolCall(fx('cost_breakdown'), 'm2'),
              ...tail,
            ]
          : [...head, { type: 'CUSTOM', name: 'waypoint.notice', value: { code: 'compose_failed', retry: true } }, ...tail]
      return new Response(sse(events), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    }),
  )
  return bodies
}

function setViewport(width: number) {
  window.matchMedia = (query: string) => {
    const min = Number(/min-width:\s*(\d+)px/.exec(query)?.[1] ?? 0)
    return {
      matches: width >= min,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    } as MediaQueryList
  }
}

const original = window.matchMedia
beforeEach(() => setViewport(390))
afterEach(() => {
  window.matchMedia = original
  vi.unstubAllGlobals()
})

describe('desktop layout', () => {
  it('≥1280px: rail, plan so far, and the latest hero widget in the canvas with a reference card in the chat', async () => {
    setViewport(1440)
    mockServer()
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="u1">
        <ChatTab demo />
      </ChatProvider>,
    )
    const canvas = await screen.findByRole('complementary', { name: 'Details' })
    // The newest hero (cost_breakdown) is in the canvas; the chat shows compact references.
    expect(await within(canvas).findByRole('button', { name: 'Use this cost' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'What it costs to open, shown on the right' })).toHaveAttribute('aria-pressed', 'true')
    const units = screen.getByRole('button', { name: 'Show Units to compare on the right' })
    // Rail: steps and the plan so far, read from display values.
    const rail = screen.getByRole('complementary', { name: 'Your journey' })
    expect(within(rail).getByRole('button', { name: 'Go back to Where' })).toBeInTheDocument()
    expect(within(rail).getByText('S$390,550')).toBeInTheDocument()
    expect(within(rail).getByRole('heading', { name: 'Demo controls' })).toBeInTheDocument()
    // Tapping an older hero brings it to the canvas.
    await user.click(units)
    expect(await within(canvas).findAllByRole('button', { name: 'Cost this unit' })).toHaveLength(3)
    await user.click(within(canvas).getByRole('button', { name: 'Back to latest' }))
    expect(await within(canvas).findByRole('button', { name: 'Use this cost' })).toBeInTheDocument()
  })

  it('1024px: rail but no canvas; hero widgets stay inline', async () => {
    setViewport(1024)
    mockServer()
    render(
      <ChatProvider threadId="u1">
        <ChatTab />
      </ChatProvider>,
    )
    expect(await screen.findByRole('button', { name: 'Use this cost' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Your journey' })).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: 'Details' })).toBeNull()
    expect(screen.queryByRole('navigation', { name: 'Your progress' })?.closest('aside')).not.toBeNull()
  })

  it('mobile: the strip, no rail, no canvas', async () => {
    mockServer()
    render(
      <ChatProvider threadId="u1">
        <ChatTab />
      </ChatProvider>,
    )
    expect(await screen.findByRole('button', { name: 'Use this cost' })).toBeInTheDocument()
    expect(screen.queryByRole('complementary')).toBeNull()
  })
})

describe('waypoint.notice', () => {
  it('shows the notice and retries composing without a user message', async () => {
    const bodies = mockServer()
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="u1">
        <ChatTab />
      </ChatProvider>,
    )
    await screen.findByRole('button', { name: 'Use this cost' })
    await user.type(screen.getByLabelText('Message Waypoint'), 'why so much?{Enter}')
    expect(await screen.findByText(/couldn't put that into words/)).toBeInTheDocument()
    const before = bodies[1]!.messages.length
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(bodies).toHaveLength(3))
    expect(bodies[2]!.forwardedProps).toEqual({ retry_compose: true })
    expect(bodies[2]!.messages.length).toBe(before)
  })
})

describe('demo controls', () => {
  it('posts weeks and scenario', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<DemoControls />)
    expect(screen.getByText('Simulated')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('What happens meanwhile'), 'sales_dip')
    await user.click(screen.getByRole('button', { name: 'Skip ahead 4 weeks' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][]
    const [, init] = calls.find(([url]) => url === 'api/demo/advance')!
    expect(JSON.parse(String(init.body))).toEqual({ weeks: 4, scenario: 'sales_dip' })
    expect(await screen.findByRole('status')).toHaveTextContent('Moved 4 weeks ahead')
  })

  it('shows a transfer Waypoint prepared and simulates signing it in WeBank', async () => {
    const pending = { id: 'si_1', status: 'pending_signature', amount: 'RMB 23k', into: 'your savings sub-account ••• 4821', start: '1 Nov 2026' }
    const fetchMock = vi.fn(async (url: string) =>
      new Response(JSON.stringify({ instructions: [url.endsWith('/sign') ? { ...pending, status: 'signed' } : pending], simulated: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<DemoControls />)
    expect(await screen.findByText(/RMB 23k into your savings sub-account ••• 4821 is waiting for your signature/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sign in WeBank' }))
    expect(await screen.findByText(/Signed in WeBank: RMB 23k a month from 1 Nov 2026/)).toBeInTheDocument()
    const sign = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) => url === 'api/demo/webank/sign')!
    expect(JSON.parse(String(sign[1].body))).toEqual({ instruction_id: 'si_1' })
  })
})
