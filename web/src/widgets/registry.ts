import type { ComponentType } from 'react'
import AlertCard from './AlertCard'
import ApprovalCard from './ApprovalCard'
import AreaCard from './AreaCard'
import AreaMap from './AreaMap'
import BusinessGlance from './BusinessGlance'
import CheckinForm from './CheckinForm'
import ClosedOptions from './ClosedOptions'
import ConfirmCard from './ConfirmCard'
import ConsentCard from './ConsentCard'
import CostBreakdown from './CostBreakdown'
import DraftCard from './DraftCard'
import FundingCompare from './FundingCompare'
import FundingMix from './FundingMix'
import FundingOptions from './FundingOptions'
import GoalSummary from './GoalSummary'
import MilestoneTimeline from './MilestoneTimeline'
import MissingItems from './MissingItems'
import PlanSummary from './PlanSummary'
import PlanVsActual from './PlanVsActual'
import ProfileCard from './ProfileCard'
import QuickReplies from './QuickReplies'
import RepairOptions from './RepairOptions'
import RuleCard from './RuleCard'
import SetasideSlider from './SetasideSlider'
import StatusCard from './StatusCard'
import TopicCard from './TopicCard'
import UnitCompare from './UnitCompare'
import UnitEconomics from './UnitEconomics'
import UploadPrompt from './UploadPrompt'
import type { Payload, WidgetProps, WidgetType } from './types'

/**
 * A display-only renderer for one widget type, keyed like a CopilotKit `ReactToolCallRenderer`
 * (`name` = the AG-UI tool call name = the widget `type`). There is deliberately no `handler`:
 * the browser never executes or answers a tool call (SPEC §2.2). Interactions leave as
 * WidgetEvents through `emit`.
 */
export interface WidgetRenderer {
  readonly name: WidgetType
  readonly render: ComponentType<WidgetProps<Payload>>
}

const table: { [K in WidgetType]: ComponentType<WidgetProps<Extract<Payload, { type?: K }>>> } = {
  quick_replies: QuickReplies,
  profile_card: ProfileCard,
  business_glance: BusinessGlance,
  consent_card: ConsentCard,
  area_map: AreaMap,
  area_card: AreaCard,
  unit_compare: UnitCompare,
  cost_breakdown: CostBreakdown,
  unit_economics: UnitEconomics,
  upload_prompt: UploadPrompt,
  missing_items: MissingItems,
  funding_options: FundingOptions,
  closed_options: ClosedOptions,
  setaside_slider: SetasideSlider,
  funding_mix: FundingMix,
  funding_compare: FundingCompare,
  milestone_timeline: MilestoneTimeline,
  goal_summary: GoalSummary,
  approval_card: ApprovalCard,
  status_card: StatusCard,
  alert_card: AlertCard,
  repair_options: RepairOptions,
  rule_card: RuleCard,
  topic_card: TopicCard,
  confirm_card: ConfirmCard,
  checkin_form: CheckinForm,
  plan_vs_actual: PlanVsActual,
  plan_summary: PlanSummary,
  draft_card: DraftCard,
}

export const widgetRenderers: readonly WidgetRenderer[] = Object.freeze(
  (Object.keys(table) as WidgetType[]).map((name) =>
    Object.freeze({ name, render: table[name] as ComponentType<WidgetProps<Payload>> }),
  ),
)

const byName = new Map(widgetRenderers.map((r) => [r.name as string, r]))

export function rendererFor(name: string): WidgetRenderer | undefined {
  return byName.get(name)
}
