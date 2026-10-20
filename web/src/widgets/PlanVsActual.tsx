import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { EChart } from '@/charts/EChart'
import { milestoneMarks } from '@/charts/milestones'
import { compactAxis, money, useChartTheme } from '@/charts/theme'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { useElementWidth } from '@/lib/useElementWidth'
import { useWidgetLayout } from './layout'
import type { PayloadOf, WidgetProps } from './types'

type View = 'savings' | 'profit'

export default function PlanVsActual({ payload: p, busy, disabled }: WidgetProps<PayloadOf<'plan_vs_actual'>>) {
  const { t, i18n } = useTranslation()
  const theme = useChartTheme()
  const tall = useWidgetLayout() === 'canvas'
  const [view, setView] = useState<View>('savings')
  const planned = view === 'savings' ? p.planned_pot : p.planned_profit
  const actual = view === 'savings' ? p.actual_pot : p.actual_profit
  const lang = i18n.language
  const currency = p.currency ?? 'CNY'
  const todayIdx = p.weeks.indexOf(p.today_week)
  const [chartRef, chartWidth] = useElementWidth<HTMLDivElement>(320)
  // Plot area is the chart width less the y-axis labels and grid padding.
  const marks = useMemo(() => milestoneMarks(p.milestones, p.weeks, chartWidth - 48), [p.milestones, p.weeks, chartWidth])

  const option = useMemo(() => {
    const fmt = (v: number) => money(v, currency, lang)
    return {
      grid: { left: 4, right: 12, top: 24, bottom: 4 },
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0]?.dataIndex ?? 0
          const a = actual[i]
          return [
            `<b>${p.month_labels[i] ?? ''}</b>`,
            `${t('w.plan_vs_actual.planned')}: ${planned[i] != null ? fmt(planned[i]!) : '—'}`,
            `${t('w.plan_vs_actual.actual')}: ${a != null ? fmt(a) : '—'}`,
          ].join('<br/>')
        },
      },
      xAxis: {
        type: 'category',
        data: p.weeks,
        boundaryGap: false,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: theme.border } },
        axisLabel: { color: theme.faint, fontSize: 10, interval: Math.max(0, Math.ceil(p.weeks.length / 5) - 1), formatter: (_: unknown, i: number) => p.month_labels[i] ?? '' },
      },
      yAxis: {
        type: 'value',
        splitNumber: 3,
        axisLabel: { color: theme.faint, fontSize: 10, formatter: (v: number) => compactAxis(v, lang) },
        splitLine: { lineStyle: { color: theme.grid } },
      },
      series: [
        {
          name: 'planned',
          type: 'line',
          data: planned,
          symbol: 'none',
          lineStyle: { color: theme.faint, width: 1.5, type: 'dashed' },
          markLine: {
            symbol: 'none',
            silent: true,
            data: [
              ...(todayIdx >= 0
                ? [{ xAxis: todayIdx, lineStyle: { color: theme.accent, width: 1.5, type: 'solid' }, label: { formatter: t('w.plan_vs_actual.today'), color: theme.accent, position: 'end' } }]
                : []),
              ...marks.map((m) => ({
                xAxis: m.x,
                lineStyle: { color: theme.border, type: 'dotted' },
                label: m.label ? { formatter: m.label, color: theme.faint, fontSize: 10, position: 'end' } : { show: false },
              })),
            ],
          },
        },
        {
          name: 'actual',
          type: 'line',
          data: actual,
          connectNulls: false,
          symbol: 'circle',
          symbolSize: 4,
          showSymbol: false,
          lineStyle: { color: theme.accent, width: 2.5 },
          itemStyle: { color: theme.accent },
        },
      ],
    }
  }, [p, planned, actual, theme, lang, t, todayIdx, currency, marks])

  const lastActual = (() => {
    for (let i = actual.length - 1; i >= 0; i--) if (actual[i] != null) return i
    return -1
  })()

  return (
    <WidgetCard
      label={t('w.plan_vs_actual.title')}
      title={t('w.plan_vs_actual.title')}
      busy={busy}
      disabled={disabled}
      aside={
        <Tabs value={view} onValueChange={(v) => setView(v as View)}>
          <TabsList aria-label={t('w.plan_vs_actual.toggle')}>
            <TabsTrigger value="savings">{t('w.plan_vs_actual.savings')}</TabsTrigger>
            <TabsTrigger value="profit">{t('w.plan_vs_actual.profit')}</TabsTrigger>
          </TabsList>
        </Tabs>
      }
    >
      {p.weeks.length === 0 ? (
        <EmptyState>{t('w.plan_vs_actual.empty')}</EmptyState>
      ) : (
        <>
          <div ref={chartRef}>
            <EChart option={option} height={tall ? 320 : 220} label={t(view === 'savings' ? 'w.plan_vs_actual.chartSavings' : 'w.plan_vs_actual.chartProfit')} />
          </div>
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-hidden>
            <li className="flex items-center gap-1.5"><span className="inline-block w-4 border-t-2 border-dashed border-faint" />{t('w.plan_vs_actual.planned')}</li>
            <li className="flex items-center gap-1.5"><span className="inline-block h-[3px] w-4 bg-accent" />{t('w.plan_vs_actual.actual')}</li>
          </ul>
          {p.milestones.length > 0 && (
            <ol className="mt-2 flex flex-col gap-0.5 text-xs">
              {p.milestones.map(([w, label], i) => (
                <li key={`${w}-${label}`} className="flex gap-2">
                  <span className="tabular w-4 text-right font-semibold text-muted">{i + 1}</span>
                  {label}
                </li>
              ))}
            </ol>
          )}
          <p className="sr-only">
            {lastActual >= 0
              ? t('w.plan_vs_actual.summary', {
                  month: p.month_labels[lastActual] ?? '',
                  actual: money(actual[lastActual]!, currency, lang),
                  planned: planned[lastActual] != null ? money(planned[lastActual]!, currency, lang) : '—',
                })
              : t('w.plan_vs_actual.noActual')}
          </p>
        </>
      )}
    </WidgetCard>
  )
}
