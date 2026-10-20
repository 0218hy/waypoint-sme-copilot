import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/contracts/types'

// Figure ids that carry a per-item part (area.<area_id>.residents, unit.<unit_id>.breakeven,
// rep.<repair_id>.likely, lvl.<cups level>.npv) share one label key per kind: fig.area.residents, fig.unit.breakeven, ...
const PER_ITEM = /^(area|unit|rep|lvl)\.[^.]+\.(.+)$/

/** The i18n key for a figure id's label, e.g. plan.open_likely -> fig.plan.open_likely. */
export function figLabelKey(id: string): string {
  const m = PER_ITEM.exec(id)
  return `fig.${m ? `${m[1]}.${m[2]}` : id}`
}

export type LooseT = (key: string, options: Record<string, unknown>) => unknown

/**
 * A figure's label in the UI language: the `fig.<id>` string when one exists, else the label the
 * server wrote (English). A label may use {{n}}, filled from the first number in the server label
 * (e.g. "Typical monthly rent for 500 sq ft"); without one, the server label is used.
 */
export function figLabel(t: LooseT, id: string, fallback: string | undefined): string {
  const fb = fallback ?? id
  if (!id.includes('.')) return fb
  const n = /\d[\d,]*/.exec(fb)?.[0]
  const v = t(figLabelKey(id), { defaultValue: '', returnObjects: true, n: n ?? '{{n}}' })
  return typeof v === 'string' && v !== '' && !v.includes('{{') ? v : fb
}

/** `(widget, id) => label` in the current language (see figLabel). */
export function useFigLabel(): (widget: Widget, id: string) => string {
  const { t } = useTranslation()
  return useCallback((widget: Widget, id: string) => figLabel(t as unknown as LooseT, id, widget.figures?.[id]?.label), [t])
}
