import { BadgeCheck, Ban, Clock, ShieldCheck, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

export default function ApprovalCard({ payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'approval_card'>>) {
  const { t, i18n } = useTranslation()
  const [sent, setSent] = useState<'approve' | 'cancel' | null>(null)
  const state = payload.state ?? 'pending'
  const pending = state === 'pending'
  const off = disabled || readOnly || !pending || sent !== null
  const data = { action: payload.action, card_hash: payload.card_hash, nonce: payload.nonce }
  return (
    <WidgetCard
      label={payload.title}
      title={
        <span className="inline-flex items-center gap-2">
          <ShieldCheck aria-hidden className="size-5 text-accent" />
          {payload.title}
        </span>
      }
      subtitle={t(`w.approval_card.action.${payload.action}`)}
      busy={busy}
      disabled={disabled}
      className={cn(pending && !disabled && 'border-accent')}
      footer={
        pending &&
        !readOnly && (
          <>
            <Button
              size="lg"
              disabled={off}
              onClick={() => {
                setSent('approve')
                emit('approve', { value: payload.nonce, data, label: t('w.approval_card.approveLabel', { title: payload.title }) })
              }}
            >
              {t('w.approval_card.approve')}
            </Button>
            <Button
              size="lg"
              variant="secondary"
              disabled={off}
              onClick={() => {
                setSent('cancel')
                emit('cancel', { value: payload.nonce, data, label: t('w.approval_card.cancel') })
              }}
            >
              {t('w.approval_card.cancel')}
            </Button>
          </>
        )
      }
    >
      <p className="text-sm text-muted">{t('w.approval_card.exactly')}</p>
      <dl className="mt-2 flex flex-col divide-y divide-border rounded-xl border border-border">
        {payload.lines.map((l) => (
          <div key={l.label} className="flex items-start justify-between gap-3 px-3 py-2 text-sm">
            <dt className="text-muted">{l.label}</dt>
            <dd className="text-right font-medium">{l.value}</dd>
          </div>
        ))}
      </dl>
      {pending && <p className="mt-2 text-xs text-faint">{t('w.approval_card.expires', { when: expiryText(payload.expires_at, i18n.language) })}</p>}
      <StateBanner state={state} refusal={payload.refusal ?? null} />
    </WidgetCard>
  )
}

function StateBanner({ state, refusal }: { state: string; refusal: string | null }) {
  const { t } = useTranslation()
  if (state === 'pending') return null
  const map = {
    approved: { Icon: BadgeCheck, cls: 'bg-success-soft text-success' },
    cancelled: { Icon: Ban, cls: 'bg-surface-2 text-muted' },
    refused: { Icon: XCircle, cls: 'bg-danger-soft text-danger' },
    expired: { Icon: Clock, cls: 'bg-warning-soft text-warning' },
  } as const
  const m = map[state as keyof typeof map]
  if (!m) return null
  return (
    <div role="status" className={cn('mt-3 flex gap-2 rounded-xl px-3 py-2 text-sm', m.cls)}>
      <m.Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div>
        <p className="font-medium">{t(`w.approval_card.state.${state as keyof typeof map}`)}</p>
        {state === 'refused' && refusal && <p>{refusal}</p>}
      </div>
    </div>
  )
}

/** The card's expiry as a local time ("4:38 AM"), with the date only when it isn't today. */
function expiryText(iso: string, lang: string): string {
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return iso
  const locale = lang === 'zh' ? 'zh-CN' : 'en-SG'
  const sameDay = when.toDateString() === new Date().toDateString()
  return new Intl.DateTimeFormat(locale, sameDay ? { timeStyle: 'short' } : { dateStyle: 'medium', timeStyle: 'short' }).format(when)
}
