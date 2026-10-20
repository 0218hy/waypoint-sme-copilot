import { Loader2, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import type { ChartSeries, Widget } from '@/contracts/types'
import { EChart } from '@/charts/EChart'
import { milestoneMarks } from '@/charts/milestones'
import { compactAxis, money, useChartTheme, type ChartTheme } from '@/charts/theme'
import { Fig } from '@/components/Fig'
import { Slider } from '@/components/ui/slider'
import { WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import { useElementWidth } from '@/lib/useElementWidth'
import { useWidgetEnv } from './env'
import { useWidgetLayout } from './layout'
import type { PayloadOf, WidgetProps } from './types'

const PREVIEW_DEBOUNCE_MS = 120
const KEYBOARD_COMMIT_MS = 700

interface Preview {
  share: number
  chart: ChartSeries
  figures: Widget['figures']
  display: Widget['display']
}

export default function SetasideSlider({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'setaside_slider'>>) {
  const { t, i18n } = useTranslation()
  const env = useWidgetEnv()
  const theme = useChartTheme()
  const tall = useWidgetLayout() === 'canvas'
  const min = payload.min ?? 0
  const max = payload.max ?? 1
  const step = payload.step ?? 0.05
  const wall = Math.max(min, Math.min(max, payload.wall))
  const off = disabled || readOnly

  const snap = useCallback((v: number) => Number((Math.round(v / step) * step).toFixed(4)), [step])
  const [share, setShare] = useState(() => Math.min(payload.share, wall))
  const [preview, setPreview] = useState<Preview | null>(null)
  const [loading, setLoading] = useState(false)
  const [previewError, setPreviewError] = useState(false)
  const [committed, setCommitted] = useState<number>(payload.share)
  const abortRef = useRef<AbortController | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const commitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pointerRef = useRef(false)

  useEffect(
    () => () => {
      abortRef.current?.abort()
      if (timerRef.current) clearTimeout(timerRef.current)
      if (commitTimerRef.current) clearTimeout(commitTimerRef.current)
    },
    [],
  )

  const requestPreview = useCallback(
    (s: number) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        abortRef.current?.abort()
        const ctrl = new AbortController()
        abortRef.current = ctrl
        setLoading(true)
        env
          .previewSetaside(payload.preview_url, s, ctrl.signal)
          .then((p) => {
            if (ctrl.signal.aborted) return
            setPreview({ share: s, chart: p.chart, figures: p.figures, display: p.display })
            setPreviewError(false)
            setLoading(false)
          })
          .catch((e: unknown) => {
            if (ctrl.signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return
            setPreviewError(true)
            setLoading(false)
          })
      }, PREVIEW_DEBOUNCE_MS)
    },
    [env, payload.preview_url],
  )

  const commit = useCallback(
    (s: number) => {
      if (commitTimerRef.current) clearTimeout(commitTimerRef.current)
      const send = () => {
        setCommitted(s)
        if (s === committed) return
        emit('slider_commit', { value: s, data: { share: s }, label: t('w.setaside_slider.commitLabel', { pct: pctText(s, i18n.language) }) })
      }
      if (pointerRef.current) {
        pointerRef.current = false
        send()
      } else {
        commitTimerRef.current = setTimeout(send, KEYBOARD_COMMIT_MS)
      }
    },
    [committed, emit, t, i18n.language],
  )

  // The widget shown merges the latest preview over the committed payload, so readouts and
  // "Where's this from?" both reflect what the chart shows.
  const view: Widget = useMemo(
    () =>
      preview && preview.share === share
        ? { ...widget, figures: { ...widget.figures, ...preview.figures }, display: { ...widget.display, ...preview.display } }
        : widget,
    [preview, share, widget],
  )
  const chart = preview && preview.share === share ? preview.chart : preview && loading ? preview.chart : payload.chart
  const stale = share !== payload.share && (!preview || preview.share !== share)

  const range = max - min || 1
  const wallPct = ((wall - min) / range) * 100
  const [chartRef, chartWidth] = useElementWidth<HTMLDivElement>(320)
  const option = useMemo(() => buildOption(chart, theme, i18n.language, t, tall, chartWidth), [chart, theme, i18n.language, t, tall, chartWidth])

  return (
    <WidgetCard
      label={t('w.setaside_slider.title')}
      title={t('w.setaside_slider.title')}
      subtitle={t('w.setaside_slider.subtitle')}
      busy={busy}
      disabled={disabled}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-xs text-muted">{t('w.setaside_slider.share')}</p>
            <p className="tabular text-4xl font-semibold leading-none tracking-tight" aria-live="polite">
              {pctText(share, i18n.language)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted">{t('w.setaside_slider.monthly')}</p>
            <p className={cn('text-lg font-semibold', stale && 'opacity-50')}>
              <Fig widget={view} id={payload.monthly_amount} />
            </p>
          </div>
        </div>

        <div>
          <Slider
            min={min}
            max={max}
            step={step}
            value={[share]}
            disabled={off}
            thumbLabel={t('w.setaside_slider.thumb')}
            aria-valuetext={t('w.setaside_slider.valueText', { pct: pctText(share, i18n.language) })}
            onPointerDown={() => {
              pointerRef.current = true
            }}
            onValueChange={([v]) => {
              if (v === undefined) return
              const s = snap(Math.min(v, wall))
              if (s === share) return
              setShare(s)
              requestPreview(s)
            }}
            onValueCommit={([v]) => {
              if (v === undefined) return
              commit(snap(Math.min(v, wall)))
            }}
            trackOverlay={
              wall < max ? (
                <span
                  aria-hidden
                  className="wall-hatch absolute inset-y-0 right-0 z-10 border-l-2 border-danger"
                  style={{ left: `${wallPct}%` }}
                />
              ) : undefined
            }
          />
          <div className="relative mt-1 h-5 text-xs text-faint" aria-hidden>
            <span className="absolute left-0">{pctText(min, i18n.language)}</span>
            {wall < max && wallPct > 12 && wallPct < 88 && (
              <span className="absolute -translate-x-1/2 font-medium text-danger" style={{ left: `${wallPct}%` }}>
                {t('w.setaside_slider.limit', { pct: pctText(wall, i18n.language) })}
              </span>
            )}
            <span className="absolute right-0">{pctText(max, i18n.language)}</span>
          </div>
          {wall < max && (
            <p className="mt-2 flex gap-2 rounded-xl bg-danger-soft/60 px-3 py-2 text-sm">
              <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
              <span>{t('w.setaside_slider.wallReason', { pct: pctText(wall, i18n.language) })}</span>
            </p>
          )}
        </div>

        <dl className={cn('grid grid-cols-2 gap-2 transition-opacity @xl:grid-cols-3', stale && 'opacity-60')}>
          <Readout label={t('w.setaside_slider.openLikely')}>
            <Fig widget={view} id={payload.open_likely} />
          </Readout>
          <Readout label={t('w.setaside_slider.openBad')}>
            <Fig widget={view} id={payload.open_p95} />
          </Readout>
          <Readout label={t('w.setaside_slider.floorRisk')} wide>
            <Fig widget={view} id={payload.floor_risk} />
          </Readout>
        </dl>

        <div className="relative" ref={chartRef}>
          <div className="mb-1 flex items-center justify-between gap-2">
            <p className="text-sm font-medium">{t('w.setaside_slider.chartTitle')}</p>
            <span className="inline-flex min-h-5 items-center gap-1 text-xs text-muted" role="status" aria-live="polite">
              {loading ? (
                <>
                  <Loader2 aria-hidden className="size-3 animate-spin motion-reduce:animate-none" />
                  {t('w.setaside_slider.updating')}
                </>
              ) : previewError ? (
                <span className="text-warning">{t('w.setaside_slider.previewError')}</span>
              ) : share !== committed ? (
                t('w.setaside_slider.preview')
              ) : null}
            </span>
          </div>
          <EChart option={option} height={tall ? 456 : 340} label={t('w.setaside_slider.chartLabel')} className={cn(stale && !loading && 'opacity-70')} />
          <ChartLegend theme={theme} />
          <MilestoneList chart={chart} />
          <ChartTable chart={chart} />
        </div>
      </div>
    </WidgetCard>
  )
}

function pctText(v: number, lang: string): string {
  return new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-SG', { style: 'percent', maximumFractionDigits: 0 }).format(v)
}

function Readout({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={cn('rounded-xl bg-surface-2 px-3 py-2', wide && 'col-span-2 @xl:col-span-1')}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="text-base font-semibold">{children}</dd>
    </div>
  )
}

function buildOption(c: ChartSeries, theme: ChartTheme, lang: string, t: TFunction, tall = false, width = 320) {
  const n = c.weeks.length
  const band = c.pot_p90.map((v, i) => Math.max(0, v - (c.pot_p10[i] ?? 0)))
  const labelEvery = Math.max(1, Math.ceil(n / 5))
  const xAxisBase = {
    type: 'category' as const,
    data: c.weeks,
    boundaryGap: false,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: theme.border } },
  }
  const yAxisBase = {
    type: 'value' as const,
    splitNumber: 3,
    axisLabel: { color: theme.faint, fontSize: 10, formatter: (v: number) => compactAxis(v, lang) },
    splitLine: { lineStyle: { color: theme.grid } },
  }
  // Plot area is the chart width less the y-axis labels and grid padding.
  const milestoneLines = milestoneMarks(c.milestones, c.weeks, width - 48).map((m) => ({
    xAxis: m.x,
    label: m.label ? { formatter: m.label, color: theme.muted, fontSize: 10, position: 'end' as const } : { show: false },
  }))
  const fmt = (v: number) => money(v, c.currency ?? 'CNY', lang)
  return {
    grid: [
      { left: 4, right: 8, top: 18, height: tall ? 250 : 170 },
      { left: 4, right: 8, top: tall ? 316 : 232, height: tall ? 110 : 80 },
    ],
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'line', link: [{ xAxisIndex: 'all' }] },
      formatter: (ps: { dataIndex: number }[]) => {
        const i = ps[0]?.dataIndex ?? 0
        const rows: [string, number | undefined][] = [
          [t('w.setaside_slider.legend.pot'), c.pot_p50[i]],
          [t('w.setaside_slider.legend.need'), c.need[i]],
          [t('w.setaside_slider.legend.home'), c.home_p50[i]],
          [t('w.setaside_slider.legend.floor'), c.floor[i]],
        ]
        return [
          `<b>${c.month_labels[i] ?? ''}</b>`,
          ...rows.filter(([, v]) => v != null).map(([k, v]) => `${k}: ${fmt(v as number)}`),
        ].join('<br/>')
      },
    },
    xAxis: [
      { ...xAxisBase, gridIndex: 0, axisLabel: { show: false } },
      {
        ...xAxisBase,
        gridIndex: 1,
        axisLabel: {
          color: theme.faint,
          fontSize: 10,
          interval: labelEvery - 1,
          formatter: (_: unknown, i: number) => c.month_labels[i] ?? '',
        },
      },
    ],
    yAxis: [
      { ...yAxisBase, gridIndex: 0 },
      { ...yAxisBase, gridIndex: 1 },
    ],
    series: [
      { name: 'p10', type: 'line', data: c.pot_p10, stack: 'pot', symbol: 'none', lineStyle: { opacity: 0 }, silent: true },
      {
        name: 'band',
        type: 'line',
        data: band,
        stack: 'pot',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: theme.band },
        silent: true,
      },
      {
        name: 'pot',
        type: 'line',
        data: c.pot_p50,
        symbol: 'none',
        lineStyle: { color: theme.accent, width: 2.5 },
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { color: theme.faint, type: 'dotted', width: 1 },
          data: milestoneLines,
        },
      },
      {
        name: 'need',
        type: 'line',
        step: 'end',
        data: c.need,
        symbol: 'none',
        lineStyle: { color: theme.text, width: 1.5, type: 'dashed' },
      },
      {
        name: 'home',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: c.home_p50,
        symbol: 'none',
        lineStyle: { color: theme.series[1], width: 2 },
      },
      {
        name: 'home_p05',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: c.home_p05,
        symbol: 'none',
        lineStyle: { color: theme.series[1], width: 1, type: 'dashed', opacity: 0.8 },
      },
      {
        name: 'floor',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: c.floor,
        symbol: 'none',
        lineStyle: { color: theme.danger, width: 1.5, type: [4, 3] },
      },
    ],
  }
}

function ChartLegend({ theme }: { theme: ChartTheme }) {
  const { t } = useTranslation()
  const items: [string, React.CSSProperties][] = [
    [t('w.setaside_slider.legend.pot'), { background: theme.accent, height: 3 }],
    [t('w.setaside_slider.legend.band'), { background: theme.band, height: 10 }],
    [t('w.setaside_slider.legend.need'), { borderTop: `2px dashed ${theme.text}` }],
    [t('w.setaside_slider.legend.home'), { background: theme.series[1], height: 3 }],
    [t('w.setaside_slider.legend.homeBad'), { borderTop: `2px dashed ${theme.series[1]}` }],
    [t('w.setaside_slider.legend.floor'), { borderTop: `2px dashed ${theme.danger}` }],
  ]
  return (
    <ul className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted" aria-hidden>
      {items.map(([label, style]) => (
        <li key={label} className="flex items-center gap-1.5">
          <span className="inline-block w-4 shrink-0" style={style} />
          {label}
        </li>
      ))}
    </ul>
  )
}

function MilestoneList({ chart }: { chart: ChartSeries }) {
  const { t } = useTranslation()
  const idx = new Map(chart.weeks.map((w, i) => [w, i]))
  if (chart.milestones.length === 0) return null
  return (
    <div className="mt-3">
      <p className="text-xs font-medium text-muted">{t('w.setaside_slider.milestones')}</p>
      <ol className="mt-1 flex flex-col gap-0.5 text-xs">
        {chart.milestones.map(([w, label], i) => (
          <li key={`${w}-${label}`} className="flex gap-2">
            <span className="tabular w-4 shrink-0 text-right font-semibold text-muted">{i + 1}</span>
            <span className="flex-1">{label}</span>
            <span className="text-faint">{chart.month_labels[idx.get(w) ?? -1] ?? ''}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** Text fallback: the chart's series at milestones and roughly quarterly. */
function ChartTable({ chart: c }: { chart: ChartSeries }) {
  const { t, i18n } = useTranslation()
  const n = c.weeks.length
  const picks = new Set<number>()
  for (let i = 0; i < n; i += 13) picks.add(i)
  if (n > 0) picks.add(n - 1)
  const idx = new Map(c.weeks.map((w, i) => [w, i]))
  for (const [w] of c.milestones) {
    const i = idx.get(w)
    if (i !== undefined) picks.add(i)
  }
  const rows = [...picks].sort((a, b) => a - b)
  const fmt = (v: number | undefined) => (v == null ? '—' : money(v, c.currency ?? 'CNY', i18n.language))
  return (
    <details className="mt-3 text-sm">
      <summary className="min-h-9 cursor-pointer py-1 text-accent underline-offset-2 hover:underline">{t('w.setaside_slider.table')}</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[28rem] text-left text-xs">
          <caption className="sr-only">{t('w.setaside_slider.chartLabel')}</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1 pr-2 font-medium">{t('w.setaside_slider.col.month')}</th>
              <th scope="col" className="py-1 pr-2 font-medium">{t('w.setaside_slider.legend.pot')}</th>
              <th scope="col" className="py-1 pr-2 font-medium">{t('w.setaside_slider.legend.need')}</th>
              <th scope="col" className="py-1 pr-2 font-medium">{t('w.setaside_slider.legend.home')}</th>
              <th scope="col" className="py-1 font-medium">{t('w.setaside_slider.legend.floor')}</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {rows.map((i) => (
              <tr key={i} className="border-t border-border">
                <th scope="row" className="py-1 pr-2 font-normal">{c.month_labels[i] ?? c.weeks[i]}</th>
                <td className="py-1 pr-2">{fmt(c.pot_p50[i])}</td>
                <td className="py-1 pr-2">{fmt(c.need[i])}</td>
                <td className="py-1 pr-2">{fmt(c.home_p50[i])}</td>
                <td className="py-1">{fmt(c.floor[i])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
