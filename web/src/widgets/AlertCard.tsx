import { AlertTriangle, Wrench } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Fig } from '@/components/Fig'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function AlertCard({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'alert_card'>>) {
  const { t } = useTranslation()
  const [sent, setSent] = useState(false)
  return (
    <WidgetCard
      label={t('w.alert_card.title')}
      title={
        <span className="inline-flex items-start gap-2">
          <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0 text-warning" />
          {payload.headline}
        </span>
      }
      className="border-warning/50"
      busy={busy}
      disabled={disabled}
      footer={
        !readOnly && !payload.resolved && (
          <Button
            disabled={disabled || sent}
            onClick={() => {
              setSent(true)
              emit('see_repairs', { value: payload.alert_id, data: { id: payload.alert_id }, label: t('w.alert_card.seeFixes') })
            }}
          >
            <Wrench aria-hidden />
            {t('w.alert_card.seeFixes')}
          </Button>
        )
      }
    >
      <dl className="grid grid-cols-2 gap-2 text-sm">
        {payload.weeks_moved && (
          <div className="rounded-xl bg-warning-soft/60 px-3 py-2">
            <dt className="text-xs text-muted">{t('w.alert_card.moved')}</dt>
            <dd className="font-semibold">
              <Fig widget={widget} id={payload.weeks_moved} />
            </dd>
          </div>
        )}
        {payload.act_by_date && (
          <div className="rounded-xl bg-surface-2 px-3 py-2">
            <dt className="text-xs text-muted">{t('w.alert_card.actBy')}</dt>
            <dd className="font-semibold">{payload.act_by_date}</dd>
          </div>
        )}
      </dl>
      <p className="mt-2 text-xs text-faint">{t('w.alert_card.kind', { kind: payload.kind })}</p>
    </WidgetCard>
  )
}
