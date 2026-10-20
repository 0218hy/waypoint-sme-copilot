import { ChevronDown, FileCheck2, Pencil } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { CostGroupRow } from '@/contracts/types'
import { EChart } from '@/charts/EChart'
import { useChartTheme } from '@/charts/theme'
import { AmountEditor } from '@/components/AmountEditor'
import { Fig, SourcePopover } from '@/components/Fig'
import { figValue } from '@/components/figValues'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function CostBreakdown({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'cost_breakdown'>>) {
  const { t } = useTranslation()
  const theme = useChartTheme()
  const [editing, setEditing] = useState<string | null>(null)
  const ro = readOnly || payload.read_only === true
  const off = disabled || ro

  const option = useMemo(() => {
    const cats = [t('w.cost_breakdown.likely'), t('w.cost_breakdown.bad')]
    return {
      grid: { left: 4, right: 8, top: 4, bottom: 4 },
      tooltip: { show: false },
      xAxis: { type: 'value', show: false },
      yAxis: {
        type: 'category',
        data: cats,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: theme.muted, fontSize: 12 },
      },
      series: payload.groups.map((g: CostGroupRow, i: number) => ({
        name: g.label,
        type: 'bar',
        stack: 'total',
        barWidth: 18,
        itemStyle: { color: theme.series[i % theme.series.length], borderColor: theme.surface, borderWidth: 1 },
        data: [figValue(widget, g.likely) ?? 0, figValue(widget, g.bad) ?? 0],
        silent: true,
      })),
    }
  }, [payload.groups, widget, theme, t])

  return (
    <WidgetCard
      label={t('w.cost_breakdown.title')}
      title={t('w.cost_breakdown.title')}
      busy={busy}
      disabled={disabled}
      footer={
        !ro && (
          <Button disabled={off || editing !== null} onClick={() => emit('confirm', { label: t('w.cost_breakdown.confirm') })} className="w-full @sm:w-auto">
            {t('w.cost_breakdown.confirm')}
          </Button>
        )
      }
    >
      {payload.groups.length === 0 ? (
        <EmptyState>{t('w.cost_breakdown.empty')}</EmptyState>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <Total label={t('w.cost_breakdown.likely')} sgd={<Fig widget={widget} id={payload.total_likely} />} cny={<Fig widget={widget} id={payload.total_likely_cny} icon={false} />} />
            <Total label={t('w.cost_breakdown.bad')} sgd={<Fig widget={widget} id={payload.total_bad} />} cny={<Fig widget={widget} id={payload.total_bad_cny} icon={false} />} tone="warning" />
          </div>
          <div>
            <EChart option={option} height={84} label={t('w.cost_breakdown.chartLabel')} />
            <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted" aria-hidden>
              {payload.groups.map((g, i) => (
                <li key={g.key} className="inline-flex items-center gap-1">
                  <span className="size-2.5 rounded-sm" style={{ background: theme.series[i % theme.series.length] }} />
                  {g.label}
                </li>
              ))}
            </ul>
          </div>
          <ul className="flex flex-col divide-y divide-border rounded-xl border border-border">
            {payload.groups.map((g) => (
              <li key={g.key}>
                <Collapsible>
                  <CollapsibleTrigger className="group flex min-h-12 w-full items-center gap-2 px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-focus">
                    <ChevronDown aria-hidden className="size-4 shrink-0 text-muted transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
                    <span className="min-w-0 flex-1 font-medium">{g.label}</span>
                    <span className="flex flex-col items-end text-sm">
                      <span className="tabular font-semibold">{widget.display?.[g.likely] ?? '—'}</span>
                      <span className="tabular text-xs text-muted">
                        {t('w.cost_breakdown.badShort')} {widget.display?.[g.bad] ?? '—'}
                      </span>
                    </span>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <ul className="flex flex-col gap-3 bg-surface-2/60 px-3 py-3">
                      {g.lines.map((l) => (
                        <li key={l.key} className="flex flex-col gap-1">
                          <div className="flex items-start justify-between gap-2">
                            <span className="text-sm font-medium">
                              {l.label}
                              {l.from_quote && (
                                <Badge tone="accent" className="ml-2 align-middle">
                                  <FileCheck2 aria-hidden className="size-3" />
                                  {t('w.cost_breakdown.fromQuote')}
                                </Badge>
                              )}
                              {(l.flags ?? []).map((f) => (
                                <Badge key={f} tone="warning" className="ml-2 align-middle">
                                  {t(`w.cost_breakdown.flag.${f}`)}
                                </Badge>
                              ))}
                            </span>
                            <span className="flex flex-col items-end text-sm">
                              <Fig widget={widget} id={l.likely} className="font-semibold" />
                              <span className="text-xs text-muted">
                                {t('w.cost_breakdown.badShort')} <Fig widget={widget} id={l.bad} icon={false} />
                              </span>
                            </span>
                          </div>
                          <div className="flex flex-wrap items-center gap-1">
                            <SourcePopover source={l.source} label={l.label} />
                            {!ro && l.editable !== false && editing !== l.key && (
                              <Button variant="ghost" size="sm" disabled={off} onClick={() => setEditing(l.key)} aria-label={t('w.cost_breakdown.editLine', { line: l.label })}>
                                <Pencil aria-hidden />
                                {t('common.edit')}
                              </Button>
                            )}
                          </div>
                          {editing === l.key && (
                            <AmountEditor
                              id={`edit-${widget.id}-${l.key}`}
                              label={t('w.cost_breakdown.newAmount', { line: l.label })}
                              currency="S$"
                              onCancel={() => setEditing(null)}
                              onSave={(amount) => {
                                setEditing(null)
                                emit('edit_line', {
                                  value: amount,
                                  data: { id: l.key, value: amount, currency: 'SGD' },
                                  label: t('w.cost_breakdown.editedLabel', { line: l.label, amount: `S$${amount}` }),
                                })
                              }}
                            />
                          )}
                        </li>
                      ))}
                    </ul>
                  </CollapsibleContent>
                </Collapsible>
              </li>
            ))}
          </ul>
        </div>
      )}
    </WidgetCard>
  )
}

function Total({ label, sgd, cny, tone }: { label: string; sgd: React.ReactNode; cny: React.ReactNode; tone?: 'warning' }) {
  return (
    <div className={tone === 'warning' ? 'rounded-xl bg-warning-soft/60 p-3' : 'rounded-xl bg-accent-soft/60 p-3'}>
      <p className="text-xs text-muted">{label}</p>
      <p className="text-lg font-semibold leading-tight">{sgd}</p>
      <p className="text-xs text-muted">{cny}</p>
    </div>
  )
}
