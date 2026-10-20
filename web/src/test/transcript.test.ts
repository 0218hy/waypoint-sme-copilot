import { renderHook } from '@testing-library/react'
import type { Message } from '@ag-ui/client'
import { describe, expect, it } from 'vitest'
import { useTranscript } from '@/chat/transcript'
import type { JourneyState } from '@/lib/api'

function call(id: string, payload: Record<string, unknown>): Message {
  return {
    id: `m_${id}`,
    role: 'assistant',
    toolCalls: [{ id, type: 'function', function: { name: String(payload.type), arguments: JSON.stringify({ id, payload, figures: {}, display: {} }) } }],
  } as unknown as Message
}

describe('useTranscript', () => {
  it("greys out the profile card's own confirm once the summary card for the step follows", () => {
    const journey = { step: 'profile' } as JourneyState
    const profile = call('w1', { type: 'profile_card', fields: [], simulated_feed: true })
    const before = renderHook(() => useTranscript([profile], journey)).result.current
    expect(before.supersededById.get('w1')).toBe(false)
    const summary = call('w2', { type: 'confirm_card', step: 'profile', title: 'Your business', items: [], confirm_label: 'ok', edit_label: 'edit' })
    const after = renderHook(() => useTranscript([profile, summary], journey)).result.current
    expect(after.supersededById.get('w1')).toBe(true)
    expect(after.supersededById.get('w2')).toBe(false)
    expect(after.replacedById.get('w1')).toBe(false)
  })

  it("keeps the goal's own timeline tappable in the Goal Keeper; the plan-step timeline greys out", () => {
    const journey = { step: 'goal_keeper' } as JourneyState
    const planTl = call('w1', { type: 'milestone_timeline', start_date: '2026-10-19', items: [] })
    const user = { id: 'u1', role: 'user', content: 'Approve' } as unknown as Message
    const goalTl = call('w2', { type: 'milestone_timeline', start_date: '2026-10-19', items: [], step: 'goal_keeper' })
    const other = call('w3', { type: 'status_card', status: 'on_track', headline: 'x', changes: [], figures: [] })
    const user2 = { id: 'u2', role: 'user', content: 'hi' } as unknown as Message
    const r = renderHook(() => useTranscript([planTl, user, goalTl, other, user2], journey)).result.current
    expect(r.supersededById.get('w2')).toBe(false)
    expect(r.supersededById.get('w1')).toBe(true)
  })
})
