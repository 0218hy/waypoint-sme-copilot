import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Fig } from '@/components/Fig'
import { useFigLabel } from '@/components/figLabel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import { useWidgetEnv } from './env'
import type { PayloadOf, WidgetProps } from './types'

const TONE = { on_track: 'success', at_risk: 'warning', off_track: 'danger' } as const

export default function StatusCard({ payload, widget, readOnly, busy, disabled }: WidgetProps<PayloadOf<'status_card'>>) {
  const { t } = useTranslation()
  const figLabel = useFigLabel()
  const env = useWidgetEnv()
  return (
    <WidgetCard
      label={t('w.status_card.title')}
      title={payload.headline}
      aside={<Badge tone={TONE[payload.status]} className="text-sm">{t(`w.status_card.status.${payload.status}`)}</Badge>}
      busy={busy}
      disabled={disabled}
      footer={
        !readOnly &&
        env.openTab && (
          <Button variant="secondary" onClick={() => env.openTab?.('goal')}>
            {t('w.status_card.openGoal')}
            <ArrowRight aria-hidden />
          </Button>
        )
      }
    >
      {payload.figures.length > 0 && (
        <dl className="grid grid-cols-2 gap-2">
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
      {payload.changes.length > 0 && (
        <section className="mt-3">
          <h4 className="text-sm font-medium">{t('w.status_card.changes')}</h4>
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {payload.changes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>
      )}
    </WidgetCard>
  )
}
