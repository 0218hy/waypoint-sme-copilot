import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { EChart } from '@/charts/EChart'
import { useChartTheme } from '@/charts/theme'
import { Fig } from '@/components/Fig'
import { figValue } from '@/components/figValues'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function FundingMix({ payload, widget, busy, disabled }: WidgetProps<PayloadOf<'funding_mix'>>) {
  const { t } = useTranslation()
  const theme = useChartTheme()
  const option = useMemo(
    () => ({
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      tooltip: { show: false },
      xAxis: { type: 'value', show: false, max: 'dataMax' },
      yAxis: { type: 'category', show: false, data: ['mix'] },
      series: payload.segments.map((s, i) => ({
        name: s.label,
        type: 'bar',
        stack: 'mix',
        barWidth: 28,
        silent: true,
        itemStyle: {
          color: theme.series[i % theme.series.length],
          borderColor: theme.surface,
          borderWidth: 2,
          borderRadius: i === 0 ? [6, 0, 0, 6] : i === payload.segments.length - 1 ? [0, 6, 6, 0] : 0,
        },
        data: [figValue(widget, s.amount) ?? 0],
      })),
    }),
    [payload.segments, widget, theme],
  )
  return (
    <WidgetCard
      label={t('w.funding_mix.title')}
      title={t('w.funding_mix.title')}
      aside={
        <span className="text-right text-sm">
          <span className="block text-xs text-muted">{t('w.funding_mix.total')}</span>
          <Fig widget={widget} id={payload.total} className="font-semibold" />
        </span>
      }
      busy={busy}
      disabled={disabled}
    >
      {payload.segments.length === 0 ? (
        <EmptyState>{t('w.funding_mix.empty')}</EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          <EChart option={option} height={32} label={t('w.funding_mix.chartLabel')} />
          <ul className="flex flex-col gap-1.5">
            {payload.segments.map((s, i) => (
              <li key={s.key} className="flex items-center justify-between gap-3 text-sm">
                <span className="flex items-center gap-2">
                  <span aria-hidden className="size-3 shrink-0 rounded-sm" style={{ background: theme.series[i % theme.series.length] }} />
                  {s.label}
                </span>
                <Fig widget={widget} id={s.amount} className="font-medium" />
              </li>
            ))}
          </ul>
        </div>
      )}
    </WidgetCard>
  )
}
