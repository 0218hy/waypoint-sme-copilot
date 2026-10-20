import { Check, ChevronDown, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { CompareColumn, Widget } from '@/contracts/types'
import { Fig } from '@/components/Fig'
import { figValue } from '@/components/figValues'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import { useElementWidth } from '@/lib/useElementWidth'
import { useWidgetEnv } from './env'
import type { PayloadOf, WidgetProps } from './types'

const PREVIEW_DEBOUNCE_MS = 300
/** Below this width the plans stack as cards instead of a table (the chat column on a desktop, a phone). */
const TABLE_MIN_PX = 560

type Row = 'savings' | 'monthly' | 'open_likely' | 'open_p95' | 'floor_risk' | 'ownership' | 'profit_share'
const ROWS: Row[] = ['savings', 'monthly', 'open_likely', 'open_p95', 'floor_risk', 'ownership', 'profit_share']

interface Preview {
  amount: string
  columns: CompareColumn[]
  figures: Widget['figures']
  display: Widget['display']
}

/** A whole number of RMB from 0 to `max`, as typed; null if it isn't one. */
function parseAmount(text: string, max: number | null): string | null {
  const s = text.trim()
  if (!/^\d+$/.test(s)) return null
  const n = Number(s)
  if (!Number.isSafeInteger(n) || (max != null && n > max)) return null
  return String(n)
}

/**
 * Compare funding plans: each column is one full solve of the plan model at the slider's share (code-computed
 * figures only). "Choose this funding" sends that column's toggle_option actions and the slider's share.
 */
export default function FundingCompare({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'funding_compare'>>) {
  const { t } = useTranslation()
  const env = useWidgetEnv()
  const off = disabled || readOnly
  const savingsCol = payload.columns.find((c) => c.savings_editable)
  const initial = savingsCol?.savings ? String(figValue(widget, savingsCol.savings) ?? '') : ''
  const max = figValue(widget, payload.savings_max)
  const [amount, setAmount] = useState(initial)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [loading, setLoading] = useState(false)
  const [previewError, setPreviewError] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const valid = parseAmount(amount, max)
  const [sizeRef, width] = useElementWidth<HTMLDivElement>(TABLE_MIN_PX)
  const wide = width >= TABLE_MIN_PX

  useEffect(
    () => () => {
      abortRef.current?.abort()
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  const requestPreview = useCallback(
    (value: string) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      abortRef.current?.abort()
      if (value === initial) {
        setPreview(null)
        setLoading(false)
        return
      }
      timerRef.current = setTimeout(() => {
        const ctrl = new AbortController()
        abortRef.current = ctrl
        setLoading(true)
        env
          .previewCompare(payload.preview_url ?? '/api/preview/compare', value, ctrl.signal)
          .then((p) => {
            if (ctrl.signal.aborted) return
            setPreview({ amount: value, columns: p.columns, figures: p.figures, display: p.display })
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
    [env, initial, payload.preview_url],
  )

  const live = preview && preview.amount === valid ? preview : null
  const view: Widget = useMemo(
    () => (live ? { ...widget, figures: { ...widget.figures, ...live.figures }, display: { ...widget.display, ...live.display } } : widget),
    [live, widget],
  )
  const columns = live?.columns ?? payload.columns
  const stale = valid !== null && valid !== initial && !live

  const choose = (c: CompareColumn) => {
    const options = (c.toggles ?? []).map((tg) => (tg.id === 'own_savings' && tg.on ? { id: tg.id, on: tg.on, amount: valid } : { id: tg.id, on: tg.on }))
    emit('toggle_option', {
      value: c.id,
      data: { column: c.id, options, share: payload.share },
      label: t('w.funding_compare.chooseLabel', { plan: c.title }),
    })
  }

  const head = (c: CompareColumn) => (
    <ColumnHead
      column={c}
      off={off}
      readOnly={readOnly}
      valid={c.savings_editable ? valid !== null : true}
      edited={c.savings_editable ? valid !== initial : false}
      onChoose={() => choose(c)}
    />
  )
  const value = (c: CompareColumn, row: Row) =>
    row === 'savings' && c.savings_editable ? (
      <SavingsInput
        value={amount}
        invalid={valid === null}
        disabled={off}
        label={t('w.funding_compare.savingsInput', { plan: c.title })}
        currency={t('w.funding_compare.rmb')}
        hint={valid === null ? t('w.funding_compare.savingsInvalid', { max: view.display?.[payload.savings_max] ?? '' }) : undefined}
        onChange={(v) => {
          setAmount(v)
          const ok = parseAmount(v, max)
          if (ok !== null) requestPreview(ok)
        }}
      />
    ) : (
      <Cell column={c} row={row} widget={view} end={!wide} />
    )

  return (
    <WidgetCard label={t('w.funding_compare.title')} title={t('w.funding_compare.title')} busy={busy} disabled={disabled}>
      {columns.length === 0 ? (
        <EmptyState>{t('w.funding_compare.empty')}</EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">
            {t('w.funding_compare.intro')} <Fig widget={view} id={payload.share_fig} />
          </p>
          <div ref={sizeRef}>
            {wide ? (
              <div className="-mx-4 overflow-x-auto px-4" tabIndex={0} role="region" aria-label={t('w.funding_compare.tableLabel')}>
                <table className="w-full border-separate border-spacing-0 text-sm">
                  <thead>
                    <tr>
                      <th scope="col" className="w-32 pb-2 text-left align-bottom text-xs font-medium text-muted">
                        <span className="sr-only">{t('w.funding_compare.rowHeader')}</span>
                      </th>
                      {columns.map((c) => (
                        <th
                          key={c.id}
                          scope="col"
                          data-column={c.id}
                          data-chosen={c.chosen || undefined}
                          className={cn('min-w-[10rem] rounded-t-xl px-2 pb-2 pt-2 text-left align-top font-normal', c.chosen && 'bg-accent-soft/50')}
                        >
                          {head(c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ROWS.map((row) => (
                      <tr key={row} data-row={row}>
                        <th scope="row" className="border-t border-border py-2 pr-2 text-left align-top text-xs font-medium text-muted">
                          {t(`w.funding_compare.row.${row}`)}
                        </th>
                        {columns.map((c) => (
                          <td key={c.id} className={cn('border-t border-border px-2 py-2 align-top', c.chosen && 'bg-accent-soft/50', stale && c.savings_editable && 'opacity-60')}>
                            {value(c, row)}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr data-row="pros_cons">
                      <th scope="row" className="border-t border-border py-2 pr-2 text-left align-top text-xs font-medium text-muted">
                        <span className="sr-only">{t('w.funding_compare.prosCons')}</span>
                      </th>
                      {columns.map((c) => (
                        <td key={c.id} className={cn('border-t border-border px-2 py-2 align-top', c.chosen && 'rounded-b-xl bg-accent-soft/50')}>
                          {c.open !== false && <ProsCons column={c} />}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              // a narrow container (the chat column, a phone): one card per plan, rows in the same order
              <ul className="flex flex-col gap-3" aria-label={t('w.funding_compare.tableLabel')}>
                {columns.map((c) => (
                  <li key={c.id} data-column={c.id} data-chosen={c.chosen || undefined} className={cn('rounded-xl border p-3', c.chosen ? 'border-accent bg-accent-soft/30' : 'border-border')}>
                    {head(c)}
                    {c.open !== false && (
                      <dl className={cn('mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 text-sm', stale && c.savings_editable && 'opacity-60')}>
                        {ROWS.filter((row) => row !== 'profit_share' || c.profit_share).map((row) => (
                          <div key={row} data-row={row} className="contents">
                            <dt className="text-xs text-muted">{t(`w.funding_compare.row.${row}`)}</dt>
                            <dd className="text-right">{value(c, row)}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {c.open !== false && (
                      <div className="mt-2">
                        <ProsCons column={c} />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="flex min-h-5 items-center gap-1.5 text-xs text-muted" aria-live="polite">
            {loading ? (
              <>
                <Loader2 aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />
                {t('w.funding_compare.updating')}
              </>
            ) : previewError && stale ? (
              t('w.funding_compare.previewError')
            ) : (
              t('w.funding_compare.note')
            )}
          </p>
        </div>
      )}
    </WidgetCard>
  )
}

function ColumnHead({
  column: c,
  off,
  readOnly,
  valid,
  edited,
  onChoose,
}: {
  column: CompareColumn
  off: boolean
  readOnly: boolean
  valid: boolean
  edited: boolean
  onChoose: () => void
}) {
  const { t } = useTranslation()
  const selected = !!c.chosen && !edited
  return (
    <div className="flex flex-col gap-1.5">
      <p className="font-semibold leading-snug">{c.title}</p>
      <p className="text-xs text-muted">{c.blurb}</p>
      {c.open === false ? (
        <div className="flex flex-col gap-1">
          <Badge tone="neutral" className="self-start">
            {t('w.funding_compare.notOpen')}
          </Badge>
          {c.why_not && <p className="text-xs text-muted">{c.why_not}</p>}
        </div>
      ) : (
        <>
          {!readOnly && (
            <Button
              size="sm"
              variant={selected ? 'soft' : 'secondary'}
              className="self-start"
              aria-pressed={selected}
              disabled={off || selected || !valid}
              onClick={onChoose}
            >
              {selected && <Check aria-hidden />}
              {t(selected ? 'w.funding_compare.selected' : 'w.funding_compare.choose')}
            </Button>
          )}
        </>
      )}
    </div>
  )
}

function ProsCons({ column: c }: { column: CompareColumn }) {
  const { t } = useTranslation()
  const word = (w: string) => t(`w.funding_options.word.${w}`, { defaultValue: w })
  const list = (items: ReactNode[]) => <ul className="ml-4 list-disc space-y-0.5">{items}</ul>
  return (
    <Collapsible>
      <CollapsibleTrigger
        className="group inline-flex min-h-8 items-center gap-0.5 rounded-md text-xs text-accent focus-visible:outline-2 focus-visible:outline-focus"
        aria-label={t('w.funding_compare.prosConsFor', { plan: c.title })}
      >
        {t('w.funding_compare.prosCons')}
        <ChevronDown aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1 flex flex-col gap-1.5 text-xs" data-pros-cons={c.id}>
          {(c.pros?.length ?? 0) > 0 && (
            <div>
              <p className="font-medium text-success">{t('w.funding_compare.pros')}</p>
              {list(c.pros!.map((w) => <li key={w} data-word={w}>{word(w)}</li>))}
            </div>
          )}
          {(c.cons?.length ?? 0) > 0 && (
            <div>
              <p className="font-medium text-warning">{t('w.funding_compare.cons')}</p>
              {list(c.cons!.map((w) => <li key={w} data-word={w}>{word(w)}</li>))}
            </div>
          )}
          {(c.terms ?? []).map((term) => (
            <div key={term.id} className="rounded-lg bg-surface-2 px-2 py-1.5">
              <p className="font-medium">{term.label}</p>
              <p>
                <span className="text-muted">{t('w.funding_options.cost')}: </span>
                {term.cost}
              </p>
              <p>
                <span className="text-muted">{t('w.funding_options.conditions')}: </span>
                {term.conditions}
              </p>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function Cell({ column: c, row, widget, end }: { column: CompareColumn; row: Row; widget: Widget; end: boolean }) {
  const { t } = useTranslation()
  const none = <span className="text-faint">{t('w.funding_compare.none')}</span>
  if (c.open === false) return none
  if (row === 'floor_risk') {
    if (!c.floor_risk) return none
    return (
      <span className={cn('inline-flex flex-col', end ? 'items-end' : 'items-start')}>
        <Fig widget={widget} id={c.floor_risk} />
        {c.floor_risk_upper && (
          <span className="text-xs text-muted">
            {t('w.funding_compare.upTo')} <Fig widget={widget} id={c.floor_risk_upper} icon={false} />
          </span>
        )}
      </span>
    )
  }
  const id = c[row]
  return id ? <Fig widget={widget} id={id} /> : none
}

function SavingsInput({
  value,
  invalid,
  disabled,
  label,
  hint,
  currency,
  onChange,
}: {
  value: string
  invalid: boolean
  disabled: boolean
  label: string
  hint?: string
  currency: string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        <span aria-hidden className="text-xs text-muted">
          {currency}
        </span>
        <Input
          className="min-h-9 px-2 text-sm"
          inputMode="numeric"
          aria-label={label}
          aria-invalid={invalid || undefined}
          disabled={disabled}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
      {hint && <p className="text-xs text-danger">{hint}</p>}
    </div>
  )
}
