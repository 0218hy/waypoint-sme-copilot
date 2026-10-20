import type { Widget } from '@/contracts/types'
import { figText } from '@/components/figValues'
import type { PayloadOf } from './types'

export type Draft = PayloadOf<'draft_card'>
export type T = (key: string, opts?: Record<string, unknown>) => string

/** The draft as plain text, for Copy and Download: the same words and figures the card shows. */
export function draftText(widget: Widget, p: Draft, t: T): string {
  const lines: string[] = [p.title]
  if (p.to) lines.push(`${t('w.draft_card.to')}: ${p.to}`)
  if (p.subject) lines.push(`${t('w.draft_card.subject')}: ${p.subject}`)
  if (p.who) lines.push(p.who)
  lines.push('')
  if (p.body) lines.push(p.body, '')
  for (const f of p.facts ?? []) lines.push(`${f.label}: ${f.figure ? (figText(widget, f.figure) ?? t('fig.missing')) : f.text}`)
  for (const it of p.items ?? []) lines.push(`[ ] ${it.text} (${t(`w.draft_card.who.${it.who}`)}; ${it.source.label})`)
  if ((p.sources ?? []).length) {
    lines.push('', `${t('fig.source')}:`)
    for (const s of p.sources ?? []) lines.push(`- ${s.label}${s.as_of ? ` (${s.as_of})` : ''}${s.url ? ` ${s.url}` : ''}`)
  }
  lines.push('', t(p.kind === 'consent_request' ? 'w.draft_card.youSend' : 'w.draft_card.youDo'))
  return lines.join('\n')
}
