import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatProvider } from '@/chat/ChatProvider'
import { ChatTab } from '@/chat/ChatTab'
import { captureEmailLink, takeEmailLink } from '@/lib/emailLink'

function fakeLocation(search: string, hash = ''): { loc: Location; history: History; replace: ReturnType<typeof vi.fn> } {
  const replace = vi.fn()
  return {
    loc: { pathname: '/app/', search, hash } as Location,
    history: { state: null, replaceState: replace } as unknown as History,
    replace,
  }
}

beforeEach(() => {
  takeEmailLink() // nothing left over from another test
  localStorage.clear()
})

describe('links from emails (?checkin= / ?alert=)', () => {
  it('reads the parameter once, clears it from the address bar and opens the chat tab', () => {
    const { loc, history, replace } = fakeLocation('?checkin=eyJn.abc123&lang=zh', '#/goal')
    expect(captureEmailLink(loc, history)).toEqual({ kind: 'checkin', value: 'eyJn.abc123' })
    expect(replace).toHaveBeenCalledWith(null, '', '/app/?lang=zh#/chat')
    expect(takeEmailLink()).toEqual({ kind: 'checkin', value: 'eyJn.abc123' })
    expect(takeEmailLink()).toBeNull()
  })

  it('an alert link is read the same way; a URL without one is left alone', () => {
    const a = fakeLocation('?alert=a_123')
    expect(captureEmailLink(a.loc, a.history)).toEqual({ kind: 'alert', value: 'a_123' })
    expect(a.replace).toHaveBeenCalledWith(null, '', '/app/#/chat')
    takeEmailLink()
    const none = fakeLocation('?email=verified')
    expect(captureEmailLink(none.loc, none.history)).toBeNull()
    expect(none.replace).not.toHaveBeenCalled()
    expect(takeEmailLink()).toBeNull()
  })

  it('survives the sign-in redirect (kept in this browser) but not for long', () => {
    const { loc, history } = fakeLocation('?alert=a_9')
    captureEmailLink(loc, history)
    const saved = localStorage.getItem('waypoint.emailLink')
    takeEmailLink() // a page reload loses the in-memory copy ...
    localStorage.setItem('waypoint.emailLink', saved!) // ... the stored one is still there
    expect(takeEmailLink()).toEqual({ kind: 'alert', value: 'a_9' })
    localStorage.setItem('waypoint.emailLink', saved!)
    expect(takeEmailLink(Date.now() + 31 * 60 * 1000)).toBeNull()
  })
})

interface RunBody {
  threadId: string
  runId: string
  forwardedProps: Record<string, unknown>
}

function mockAgui(firstEvents: object[]) {
  const bodies: RunBody[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as RunBody
      bodies.push(body)
      const events = [
        { type: 'RUN_STARTED', threadId: body.threadId, runId: body.runId },
        ...(bodies.length === 1 ? firstEvents : []),
        { type: 'RUN_FINISHED', threadId: body.threadId, runId: body.runId },
      ]
      return new Response(events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(''), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      })
    }),
  )
  return bodies
}

afterEach(() => vi.unstubAllGlobals())

describe('the chat opens an email link once', () => {
  it('sends it with the opening run only; the server decides what it opens', async () => {
    const bodies = mockAgui([])
    const user = userEvent.setup()
    render(
      <ChatProvider threadId="j_1" takeLink={() => ({ kind: 'alert', value: 'a_1' })}>
        <ChatTab />
      </ChatProvider>,
    )
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]!.forwardedProps).toEqual({ email_link: { kind: 'alert', value: 'a_1' } })
    await user.type(screen.getByLabelText('Message Waypoint'), 'hello{Enter}')
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1]!.forwardedProps).toEqual({})
  })

  it('a link the server refuses shows a plain notice, with nothing to retry', async () => {
    mockAgui([{ type: 'CUSTOM', name: 'waypoint.notice', value: { code: 'link_invalid', retry: false } }])
    render(
      <ChatProvider threadId="j_1" takeLink={() => ({ kind: 'checkin', value: 'forged.sig' })}>
        <ChatTab />
      </ChatProvider>,
    )
    expect(await screen.findByText(/link from your email has expired or isn't valid/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
  })
})
