import { Check, ClipboardCopy, Download, FileText, ListChecks, Send } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Fig, SourceLine } from '@/components/Fig'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import { draftText, type Draft, type T } from './draftText'
import type { WidgetProps } from './types'

export default function DraftCard({ widget, payload, busy, disabled }: WidgetProps<Draft>) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState<'idle' | 'copied' | 'failed'>('idle')
  const letter = payload.kind === 'consent_request'
  const text = () => draftText(widget, payload, t as unknown as T)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text())
      setCopied('copied')
    } catch {
      setCopied('failed')
    }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([text()], { type: 'text/plain;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = payload.filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const Icon = letter ? FileText : ListChecks
  return (
    <WidgetCard
      label={payload.title}
      title={
        <span className="inline-flex items-start gap-2">
          <Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-accent" />
          {payload.title}
        </span>
      }
      subtitle={payload.who || undefined}
      aside={<Badge tone="neutral">{t('w.draft_card.draft')}</Badge>}
      busy={busy}
      disabled={disabled}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={copy} aria-label={t('w.draft_card.copyAria', { title: payload.title })}>
            {copied === 'copied' ? <Check aria-hidden /> : <ClipboardCopy aria-hidden />}
            {copied === 'copied' ? t('w.draft_card.copied') : t('w.draft_card.copy')}
          </Button>
          <Button variant="secondary" size="sm" onClick={download} aria-label={t('w.draft_card.downloadAria', { title: payload.title })}>
            <Download aria-hidden />
            {t('w.draft_card.download')}
          </Button>
          {copied === 'failed' && (
            <span role="alert" className="text-xs text-danger">
              {t('w.draft_card.copyFailed')}
            </span>
          )}
        </>
      }
    >
      {letter && (
        <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-faint">{t('w.draft_card.to')}</dt>
          <dd>{payload.to}</dd>
          <dt className="text-faint">{t('w.draft_card.subject')}</dt>
          <dd className="font-medium">{payload.subject}</dd>
        </dl>
      )}
      {letter &&
        (payload.body ? (
          <div className="whitespace-pre-line rounded-xl border border-border bg-surface-2 px-3 py-2 text-[15px]">{payload.body}</div>
        ) : (
          <p className="rounded-xl bg-surface-2 px-3 py-2 text-sm text-muted">{t('w.draft_card.noBody')}</p>
        ))}
      {(payload.facts ?? []).length > 0 && (
        <section className="mt-3">
          <h4 className="text-sm font-medium">{t('w.draft_card.facts')}</h4>
          <dl className="mt-1 divide-y divide-border text-sm">
            {(payload.facts ?? []).map((f) => (
              <div key={f.label} className="flex flex-wrap justify-between gap-x-3 py-1.5">
                <dt className="text-muted">{f.label}</dt>
                <dd className="text-right font-medium">{f.figure ? <Fig widget={widget} id={f.figure} /> : f.text}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {(payload.items ?? []).length > 0 && (
        <ul className="flex flex-col gap-2">
          {(payload.items ?? []).map((it) => (
            <li key={it.id} className="rounded-xl bg-surface-2 px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[15px] leading-snug">{it.text}</p>
                <Badge tone="neutral" className="shrink-0">
                  {t(`w.draft_card.who.${it.who}`)}
                </Badge>
              </div>
              <SourceLine source={it.source} className="mt-1" />
            </li>
          ))}
        </ul>
      )}
      {letter && (payload.sources ?? []).map((s) => <SourceLine key={s.label} source={s} className="mt-2" />)}
      {!letter && payload.as_of && <p className="mt-2 text-xs text-faint">{t('w.draft_card.asOf', { date: payload.as_of })}</p>}
      <p className="mt-3 inline-flex items-start gap-1.5 text-xs text-muted">
        <Send aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        {t(letter ? 'w.draft_card.youSend' : 'w.draft_card.youDo')}
      </p>
    </WidgetCard>
  )
}
