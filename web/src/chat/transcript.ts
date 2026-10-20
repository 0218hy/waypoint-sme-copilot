import type { Message } from '@ag-ui/client'
import { useMemo } from 'react'
import type { Widget } from '@/contracts/types'
import type { JourneyState } from '@/lib/api'
import { SINGLE_SHOT, WIDGET_STEP, type WidgetType } from '@/widgets/types'

export interface ToolEntry {
  /** Tool call id (= widget id). */
  key: string
  msgIdx: number
  name: string
  widget: Widget | null
}

/** Large widgets that the desktop layout shows in the canvas pane. */
export const HERO_TYPES: ReadonlySet<string> = new Set<WidgetType>([
  'area_map',
  'unit_compare',
  'cost_breakdown',
  'setaside_slider',
  'milestone_timeline',
  'plan_vs_actual',
])

export function parseWidget(args: string): Widget | null {
  if (!args) return null
  try {
    const w = JSON.parse(args) as Widget
    return w && typeof w === 'object' && w.payload ? w : null
  } catch {
    return null
  }
}

export interface Transcript {
  entries: ToolEntry[]
  byKey: Map<string, ToolEntry>
  /** INTERFACES §1: superseded by a newer widget of its type, or the step has moved on. */
  supersededById: Map<string, boolean>
  /** A newer widget of the same type exists (only this one is an "earlier version"). */
  replacedById: Map<string, boolean>
  lastUserIdx: number
  latestHero: ToolEntry | undefined
}

export function useTranscript(messages: Message[], journey: JourneyState | null): Transcript {
  const step = journey?.step
  return useMemo(() => {
    const entries: ToolEntry[] = []
    messages.forEach((msg, msgIdx) => {
      if (msg.role !== 'assistant' || !msg.toolCalls) return
      for (const tc of msg.toolCalls) entries.push({ key: tc.id, msgIdx, name: tc.function.name, widget: parseWidget(tc.function.arguments) })
    })
    let lastUserIdx = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]!.role === 'user') {
        lastUserIdx = i
        break
      }
    }
    const supersededById = new Map<string, boolean>()
    const replacedById = new Map<string, boolean>()
    entries.forEach((e, k) => {
      const newer = entries.slice(k + 1).some((o) => o.name === e.name)
      replacedById.set(e.key, newer)
      const current = e.msgIdx > lastUserIdx
      const payload = e.widget?.payload
      const widgetStep =
        payload?.type === 'confirm_card' || payload?.type === 'milestone_timeline'
          ? (payload.step ?? WIDGET_STEP[e.name as WidgetType])
          : WIDGET_STEP[e.name as WidgetType]
      const stepMoved = !current && !!widgetStep && !!step && widgetStep !== step
      const answered = !current && SINGLE_SHOT.has(e.name as WidgetType)
      // the profile card's own "That's right" gives way to the summary card that follows it
      const summarised =
        e.name === 'profile_card' &&
        entries.slice(k + 1).some((o) => o.widget?.payload.type === 'confirm_card' && o.widget.payload.step === 'profile')
      supersededById.set(e.key, newer || stepMoved || answered || summarised)
    })
    const latestHero = [...entries].reverse().find((e) => HERO_TYPES.has(e.name) && e.widget)
    return { entries, byKey: new Map(entries.map((e) => [e.key, e])), supersededById, replacedById, lastUserIdx, latestHero }
  }, [messages, step])
}

/** The newest widget of a type in the transcript (for the read-only "plan so far"). */
export function latestOf<T extends WidgetType>(entries: ToolEntry[], type: T): (Widget & { payload: Extract<Widget['payload'], { type?: T }> }) | undefined {
  for (let i = entries.length - 1; i >= 0; i--) {
    const w = entries[i]!.widget
    if (w?.payload.type === type) return w as Widget & { payload: Extract<Widget['payload'], { type?: T }> }
  }
  return undefined
}
