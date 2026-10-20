import type { Widget } from '@/contracts/types'

/** The display text for a Figure id. Never formats numbers itself (INTERFACES §3). */
export function figText(widget: Widget, id: string | null | undefined): string | undefined {
  if (!id) return undefined
  return widget.display?.[id]
}

export function figValue(widget: Widget, id: string | null | undefined): number | null {
  if (!id) return null
  const v = widget.figures?.[id]?.value
  if (v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
