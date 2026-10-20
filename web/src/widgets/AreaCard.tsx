import { ArrowLeft, Star } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Fig, SourceLine } from '@/components/Fig'
import { useFigLabel } from '@/components/figLabel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function AreaCard({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'area_card'>>) {
  const { t, i18n } = useTranslation()
  const figLabel = useFigLabel()
  const off = disabled || readOnly
  const pct = (v: number) =>
    new Intl.NumberFormat(i18n.language === 'zh' ? 'zh-CN' : 'en-SG', { style: 'percent', maximumFractionDigits: 0 }).format(v)
  const bands = Object.entries(payload.age_bands ?? {}).filter((e): e is [string, number] => typeof e[1] === 'number')
  const maxBand = Math.max(0.0001, ...bands.map(([, v]) => v))
  return (
    <WidgetCard
      label={payload.name}
      title={payload.name}
      subtitle={t('w.area_card.score', { score: Math.round(payload.score) })}
      aside={(payload.simulated_fields?.length ?? 0) > 0 ? <Badge tone="warning">{t('common.simulated')}</Badge> : undefined}
      busy={busy}
      disabled={disabled}
      footer={
        !readOnly && (
          <>
            <Button disabled={off} onClick={() => emit('shortlist', { value: payload.area_id, data: { id: payload.area_id }, label: t('w.area_card.shortlistLabel', { name: payload.name }) })}>
              <Star aria-hidden />
              {t('w.area_card.shortlist')}
            </Button>
            <Button variant="ghost" disabled={off} onClick={() => emit('back', { value: payload.area_id, label: t('w.area_card.back') })}>
              <ArrowLeft aria-hidden />
              {t('w.area_card.back')}
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-4">
        {payload.stats.length > 0 && (
          <dl className="grid grid-cols-1 gap-x-4 gap-y-2 @md:grid-cols-2">
            {payload.stats.map((id) => (
              <div key={id} className="flex items-baseline justify-between gap-2 border-b border-border pb-1.5 @md:block @md:border-0">
                <dt className="text-sm text-muted">{figLabel(widget, id)}</dt>
                <dd className="text-right font-semibold @md:text-left">
                  <Fig widget={widget} id={id} />
                </dd>
              </div>
            ))}
          </dl>
        )}

        {bands.length > 0 && (
          <section>
            <h4 className="text-sm font-medium">{t('w.area_card.ages')}</h4>
            <ul className="mt-2 flex flex-col gap-1.5">
              {bands.map(([band, v]) => (
                <li key={band} className="grid grid-cols-[4rem_1fr_3rem] items-center gap-2 text-sm">
                  <span className="text-muted">{band}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                    <span className="block h-full rounded-full bg-accent" style={{ width: `${(v / maxBand) * 100}%` }} />
                  </span>
                  <span className="tabular text-right">{pct(v)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {payload.factors.length > 0 && (
          <section>
            <h4 className="text-sm font-medium">{t('w.area_card.why')}</h4>
            <ul className="mt-2 flex flex-col gap-2.5">
              {payload.factors.map((f) => (
                <li key={f.key}>
                  <div className="flex items-baseline justify-between gap-2 text-sm">
                    <span className="font-medium">{f.label}</span>
                    <span className="tabular text-muted">
                      {t('w.area_card.points', { points: Math.round(f.points), max: Math.round(f.max_points) })}
                    </span>
                  </div>
                  <div
                    className="mt-1 h-2 overflow-hidden rounded-full bg-surface-3"
                    role="meter"
                    aria-label={f.label}
                    aria-valuemin={0}
                    aria-valuemax={f.max_points}
                    aria-valuenow={f.points}
                  >
                    <div className="h-full rounded-full bg-accent" style={{ width: `${f.max_points > 0 ? (f.points / f.max_points) * 100 : 0}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-muted">{f.detail}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {(payload.simulated_fields?.length ?? 0) > 0 && (
          <p className="rounded-lg bg-warning-soft px-2 py-1.5 text-xs text-warning">
            {t('w.area_card.simulatedNote', { fields: payload.simulated_fields!.join(', ') })}
          </p>
        )}
        {payload.sources.map((s) => (
          <SourceLine key={s.label} source={s} />
        ))}
      </div>
    </WidgetCard>
  )
}
