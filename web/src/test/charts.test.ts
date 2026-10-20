import { afterEach, describe, expect, it } from 'vitest'
import { groupLabel, milestoneMarks } from '@/charts/milestones'
import { figLabel, figLabelKey, type LooseT } from '@/components/figLabel'
import i18n from '@/i18n'

const weeks = Array.from({ length: 105 }, (_, i) => i)
const ms: [number, string][] = [
  [3, 'Lender consent'],
  [9, 'ODI filing'],
  [14, 'Setup transfer'],
  [40, 'First main transfer'],
  [41, 'Sign the lease'],
  [42, 'Fit-out starts'],
  [62, 'Open'],
]

describe('milestone markers', () => {
  it('groups milestones that would overlap on a phone-width chart', () => {
    const marks = milestoneMarks(ms, weeks, 330)
    expect(marks.map((m) => m.x)).toEqual([3, 9, 14, 40, 41, 42, 62])
    expect(marks.filter((m) => m.label).map((m) => m.label)).toEqual(['1–2', '3', '4–6', '7'])
  })

  it('keeps separate labels when there is room, but still merges same-fortnight weeks', () => {
    const marks = milestoneMarks(ms, weeks, 1300)
    expect(marks.filter((m) => m.label).map((m) => m.label)).toEqual(['1', '2', '3', '4–6', '7'])
  })

  it('numbers match the list even when a milestone is off the chart', () => {
    const marks = milestoneMarks([[200, 'Later'], ...ms.slice(0, 2)], weeks, 1300)
    expect(marks).toEqual([
      { x: 3, label: '2' },
      { x: 9, label: '3' },
    ])
    expect(groupLabel([5, 7])).toBe('5, 7')
  })
})

describe('figure labels', () => {
  afterEach(() => i18n.changeLanguage('en'))
  const t = i18n.t.bind(i18n) as unknown as LooseT

  it('uses the zh label by figure id and falls back to the server label', async () => {
    await i18n.changeLanguage('zh')
    expect(figLabel(t, 'plan.open_likely', 'Likely opening')).toBe('预计开业')
    expect(figLabel(t, 'area.bedok.residents', 'Residents')).toBe('居民人数')
    expect(figLabel(t, 'area.bedok.rent_typical', 'Typical monthly rent for 500 sq ft')).toBe('500 平方英尺的常见月租')
    expect(figLabel(t, 'area.bedok.rent_typical', 'Typical monthly rent')).toBe('Typical monthly rent')
    expect(figLabel(t, 'param.fx_cny_per_sgd', 'FX rate')).toBe('FX rate')
    expect(figLabel(t, 'cost.total', 'Total')).toBe('Total')
    expect(figLabel(t, 'f_open', 'Likely opening')).toBe('Likely opening')
    expect(figLabelKey('unit.u12.breakeven')).toBe('fig.unit.breakeven')
  })
})
