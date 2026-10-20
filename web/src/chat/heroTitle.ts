/** Widgets that can sit large in the desktop canvas, with a one-line reference in the chat. */
export type HeroType = 'area_map' | 'unit_compare' | 'cost_breakdown' | 'setaside_slider' | 'milestone_timeline' | 'plan_vs_actual'

export function heroTitleKey(type: HeroType) {
  return `w.${type}.title` as const
}
