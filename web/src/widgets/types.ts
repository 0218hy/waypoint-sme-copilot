import type { Widget, WidgetEvent } from '@/contracts/types'

export type Payload = Widget['payload']
export type WidgetType = NonNullable<Payload['type']>
export type PayloadOf<T extends WidgetType> = Extract<Payload, { type?: T }>
export type EventName = WidgetEvent['event']

export interface EmitOptions {
  value?: unknown
  data?: Record<string, unknown>
  /** Short, human-readable text for the transcript (INTERFACES §1). The server never acts on it. */
  label: string
}

/** Sends one structured WidgetEvent for this widget. */
export type Emit = (event: EventName, opts: EmitOptions) => void

export interface WidgetProps<P extends Payload = Payload> {
  widget: Widget
  payload: P
  emit: Emit
  /** Superseded by a newer widget, the step moved on, or a run is in progress. */
  disabled: boolean
  /** Goal tab: display only. */
  readOnly: boolean
  /** The server is working on this widget (journey state `busy_widget`). */
  busy: boolean
}

/** The six step ids a widget belongs to, used only to grey out widgets once the step moves on. */
export const WIDGET_STEP: Partial<Record<WidgetType, string>> = {
  consent_card: 'welcome',
  profile_card: 'profile',
  business_glance: 'profile',
  area_map: 'site',
  area_card: 'site',
  unit_compare: 'site',
  cost_breakdown: 'cost',
  unit_economics: 'cost',
  upload_prompt: 'cost',
  missing_items: 'cost',
  funding_options: 'funding',
  closed_options: 'funding',
  setaside_slider: 'funding',
  funding_mix: 'funding',
  funding_compare: 'funding',
  milestone_timeline: 'goal_plan',
  goal_summary: 'goal_plan',
  status_card: 'goal_keeper',
  alert_card: 'goal_keeper',
  repair_options: 'goal_keeper',
  checkin_form: 'goal_keeper',
}

/** Widgets answered once: after the owner has replied to anything later, they are history. */
export const SINGLE_SHOT: ReadonlySet<WidgetType> = new Set<WidgetType>([
  'quick_replies',
  'confirm_card',
  'consent_card',
  'rule_card',
  'approval_card',
  'repair_options',
  'alert_card',
  'goal_summary',
  'checkin_form',
  'area_card',
])

export const ALL_WIDGET_TYPES: readonly WidgetType[] = [
  'quick_replies',
  'profile_card',
  'business_glance',
  'consent_card',
  'area_map',
  'area_card',
  'unit_compare',
  'cost_breakdown',
  'unit_economics',
  'upload_prompt',
  'missing_items',
  'funding_options',
  'closed_options',
  'setaside_slider',
  'funding_mix',
  'funding_compare',
  'milestone_timeline',
  'goal_summary',
  'approval_card',
  'status_card',
  'alert_card',
  'repair_options',
  'rule_card',
  'topic_card',
  'confirm_card',
  'checkin_form',
  'plan_vs_actual',
  'plan_summary',
  'draft_card',
]
