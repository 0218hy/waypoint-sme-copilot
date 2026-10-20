import { ChevronDown, Coins, TriangleAlert } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { EconLine, Widget } from '@/contracts/types'
import { EChart } from '@/charts/EChart'
import { useChartTheme } from '@/charts/theme'
import { Fig, SourceLine } from '@/components/Fig'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

const PNL_COLS = ['revenue', 'ebitda', 'margin', 'tax', 'net', 'payback_likely', 'payback_bad', 'npv'] as const

/** "Unit economics & payback" (tools/unit_econ.py). Every number is a Figure from the server. */
export default function UnitEconomics({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'unit_economics'>>) {
  const { t } = useTranslation()
  const theme = useChartTheme()
  const inputId = useId()
  const [cups, setCups] = useState(payload.owner_cups != null ? String(payload.owner_cups) : '')
  const [error, setError] = useState(false)
  const off = disabled || readOnly
  const canEdit = !readOnly && payload.editable !== false

  const ramp = useMemo(
    () => ({
      grid: { left: 4, right: 4, top: 8, bottom: 4 },
      tooltip: { show: false },
      xAxis: { type: 'category', show: false, data: payload.ramp_likely.map((_, i) => i) },
      yAxis: { type: 'value', show: false, min: 0, max: 1 },
      series: [
        { type: 'line', data: payload.ramp_likely, smooth: true, symbol: 'none', lineStyle: { color: theme.accent, width: 2 }, silent: true },
        { type: 'line', data: payload.ramp_bad, smooth: true, symbol: 'none', lineStyle: { color: theme.warning, width: 2, type: 'dashed' }, silent: true },
      ],
    }),
    [payload.ramp_likely, payload.ramp_bad, theme],
  )

  const submit = () => {
    const n = Number(cups.trim())
    if (!Number.isInteger(n) || n <= 0 || n > 2000) {
      setError(true)
      return
    }
    setError(false)
    emit('edit', { value: n, data: { field: 'owner_cups', cups: n }, label: t('w.unit_economics.ownerLabel', { cups: n }) })
  }

  return (
    <WidgetCard
      label={t('w.unit_economics.title')}
      title={
        <span className="inline-flex items-center gap-2">
          <Coins aria-hidden className="size-5 text-accent" />
          {t('w.unit_economics.title')}
        </span>
      }
      subtitle={payload.unit_name}
      aside={<Badge tone="warning">{t('w.unit_economics.estimate')}</Badge>}
      busy={busy}
      disabled={disabled}
      footer={
        payload.benchmarks.length > 0 && (
          <div className="flex w-full flex-col gap-1">
            <p className="text-xs font-medium text-muted">{t('w.unit_economics.benchmarks')}</p>
            <ul className="flex flex-col gap-1">
              {payload.benchmarks.map((b) => (
                <li key={b.figure} className="flex flex-col text-xs @md:flex-row @md:items-baseline @md:justify-between @md:gap-3">
                  <span>
                    {b.label}: <Fig widget={widget} id={b.figure} className="font-medium" />
                  </span>
                  <SourceLine source={b.source} />
                </li>
              ))}
            </ul>
            <p className="text-xs text-faint">{t('w.unit_economics.benchmarksNote')}</p>
          </div>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <dl className="grid grid-cols-1 gap-2 @sm:grid-cols-2">
          {payload.headline.map((l, i) => (
            <div key={l.key} className={cn('rounded-xl px-3 py-2', i === 1 ? 'bg-accent-soft/60' : 'bg-surface-2')}>
              <dt className="flex items-center gap-1 text-xs text-muted">
                {l.label}
                {l.estimate && <span className="text-warning">· {t('w.unit_economics.estimateShort')}</span>}
              </dt>
              <dd className="text-lg font-semibold leading-tight">
                <Fig widget={widget} id={l.figure} />
              </dd>
            </div>
          ))}
        </dl>

        <div>
          <p className="mb-1 text-sm font-medium">{t('w.unit_economics.pnl')}</p>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-[640px] whitespace-nowrap text-sm">
              <caption className="sr-only">{t('w.unit_economics.pnl')}</caption>
              <thead className="bg-surface-2 text-xs text-muted">
                <tr>
                  <th scope="col" className="px-2 py-1.5 text-left font-medium">
                    {t('w.unit_economics.col.cups')}
                  </th>
                  {PNL_COLS.map((c) => (
                    <th key={c} scope="col" className="px-2 py-1.5 text-right font-medium">
                      {t(`w.unit_economics.col.${c}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {payload.rows.map((r) => (
                  <tr key={r.key} className={cn(r.owner && 'bg-accent-soft/40')}>
                    <th scope="row" className="px-2 py-1.5 text-left font-medium">
                      <Fig widget={widget} id={r.cups} icon={false} />
                      {r.owner && <span className="ml-1 text-xs text-accent">{t('w.unit_economics.yours')}</span>}
                      {r.registered && (
                        <Badge tone="neutral" className="ml-1 align-middle">
                          {t('w.unit_economics.gstRegistered')}
                        </Badge>
                      )}
                    </th>
                    {PNL_COLS.map((c) => (
                      <td key={c} className="px-2 py-1.5 text-right tabular">
                        <Fig widget={widget} id={r[c]} icon={false} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-xs text-muted">{t('w.unit_economics.pnlNote')}</p>
        </div>

        {canEdit && (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
          >
            <label htmlFor={inputId} className="flex flex-col gap-1 text-sm">
              <span className="font-medium">{t('w.unit_economics.ownerQuestion')}</span>
              <Input
                id={inputId}
                inputMode="numeric"
                value={cups}
                onChange={(e) => setCups(e.target.value)}
                aria-invalid={error || undefined}
                className="w-36"
                disabled={off}
              />
            </label>
            <Button type="submit" variant="secondary" disabled={off || cups.trim() === ''}>
              {t('w.unit_economics.ownerSubmit')}
            </Button>
            {error && <p className="w-full text-xs text-danger">{t('w.unit_economics.ownerError')}</p>}
          </form>
        )}

        {payload.chain && payload.chain.length > 0 && (
          <Section title={t('w.unit_economics.chain')} open>
            <dl className="flex flex-col gap-1.5">
              {payload.chain.map((r) => (
                <div key={r.key} className="flex flex-col gap-0.5 text-sm">
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-muted">{r.label}</dt>
                    <dd className="text-right font-semibold">
                      <Fig widget={widget} id={r.figure} />
                    </dd>
                  </div>
                  {r.compare && (
                    <div className="flex items-start justify-between gap-3 text-xs">
                      <span className="text-faint">{r.compare_label}</span>
                      <Fig widget={widget} id={r.compare} className="text-muted" />
                    </div>
                  )}
                </div>
              ))}
            </dl>
          </Section>
        )}
        <Section title={t('w.unit_economics.perCup')}>
          <Lines lines={payload.per_cup} widget={widget} />
        </Section>
        <Section title={t('w.unit_economics.fixed')}>
          <Lines lines={payload.fixed} widget={widget} />
        </Section>
        <Section title={t('w.unit_economics.investment')}>
          <Lines lines={payload.investment} widget={widget} />
        </Section>
        <Section title={t('w.unit_economics.sensitivity')}>
          <Lines lines={payload.sensitivity} widget={widget} />
        </Section>
        <Section title={t('w.unit_economics.ramp')}>
          <EChart option={ramp} height={90} label={t('w.unit_economics.rampLabel')} />
          <ul className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted" aria-hidden>
            <li className="inline-flex items-center gap-1">
              <span className="h-0.5 w-4" style={{ background: theme.accent }} />
              {t('w.unit_economics.rampLikely')}
            </li>
            <li className="inline-flex items-center gap-1">
              <span className="h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: theme.warning }} />
              {t('w.unit_economics.rampBad')}
            </li>
          </ul>
          <p className="mt-1 inline-flex items-start gap-1 text-xs text-warning">
            <TriangleAlert aria-hidden className="mt-0.5 size-3 shrink-0" />
            {t('w.unit_economics.rampNote')}
          </p>
        </Section>
        {payload.notes && payload.notes.length > 0 && (
          <ul className="flex list-disc flex-col gap-1 pl-4 text-xs text-muted">
            {payload.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
      </div>
    </WidgetCard>
  )
}

function Section({ title, open, children }: { title: string; open?: boolean; children: React.ReactNode }) {
  return (
    <Collapsible defaultOpen={open} className="rounded-xl border border-border">
      <CollapsibleTrigger className="group flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium focus-visible:outline-2 focus-visible:outline-focus">
        <ChevronDown aria-hidden className="size-4 shrink-0 text-muted transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-3">{children}</CollapsibleContent>
    </Collapsible>
  )
}

function Lines({ lines, widget }: { lines: EconLine[]; widget: Widget }) {
  const { t } = useTranslation()
  return (
    <dl className="flex flex-col divide-y divide-border">
      {lines.map((l) => (
        <div key={l.key} className="flex items-start justify-between gap-3 py-1.5 text-sm">
          <dt className="text-muted">
            {l.label}
            {l.estimate && <span className="ml-1 text-xs text-warning">· {t('w.unit_economics.estimateShort')}</span>}
          </dt>
          <dd className="text-right font-medium">
            <Fig widget={widget} id={l.figure} />
          </dd>
        </div>
      ))}
    </dl>
  )
}
