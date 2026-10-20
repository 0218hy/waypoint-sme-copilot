import { Coins, MapPin, MessageSquare, Receipt } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Fig } from '@/components/Fig'
import { useFigLabel } from '@/components/figLabel'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import { useWidgetEnv } from './env'
import type { PayloadOf, WidgetProps } from './types'

const ICON = { site: MapPin, cost: Receipt, funding: Coins } as const

export default function PlanSummary({ payload, widget, emit, disabled, busy }: WidgetProps<PayloadOf<'plan_summary'>>) {
  const { t } = useTranslation()
  const figLabel = useFigLabel()
  const env = useWidgetEnv()
  const Icon = ICON[payload.kind]
  return (
    <WidgetCard
      label={payload.title}
      title={
        <span className="inline-flex items-center gap-2">
          <Icon aria-hidden className="size-5 text-accent" />
          {payload.title}
        </span>
      }
      subtitle={t(`w.plan_summary.heading.${payload.kind}`)}
      busy={busy}
      disabled={disabled}
      footer={
        <Button
          variant="secondary"
          disabled={disabled}
          onClick={() => {
            env.openTab?.('chat')
            emit('reopen_step', {
              value: payload.reopen_step,
              data: { step: payload.reopen_step },
              label: t('w.plan_summary.changeLabel', { what: t(`w.plan_summary.kind.${payload.kind}`) }),
            })
          }}
        >
          <MessageSquare aria-hidden />
          {t('w.plan_summary.change')}
        </Button>
      }
    >
      <dl className="flex flex-col divide-y divide-border">
        {payload.lines.map((l) => (
          <div key={l.label} className="flex items-start justify-between gap-3 py-2 text-sm first:pt-0">
            <dt className="text-muted">{l.label}</dt>
            <dd className="text-right font-medium">{l.value}</dd>
          </div>
        ))}
      </dl>
      {payload.figures.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-2">
          {payload.figures.map((id) => (
            <div key={id} className="rounded-xl bg-surface-2 px-3 py-2">
              <dt className="text-xs text-muted">{figLabel(widget, id)}</dt>
              <dd className="font-semibold">
                <Fig widget={widget} id={id} />
              </dd>
            </div>
          ))}
        </dl>
      )}
    </WidgetCard>
  )
}
