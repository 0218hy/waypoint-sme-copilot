import { ChevronDown, Landmark } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Fig, SourceLine } from '@/components/Fig'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Switch } from '@/components/ui/switch'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { FundingCard } from '@/contracts/types'
import type { PayloadOf, WidgetProps } from './types'

const STATUS_TONE = { open: 'success', optional: 'info', closed: 'danger', later: 'neutral' } as const

/** Ranking words (tools/funding.rank_options): the ones that cost the owner something read as a caution. */
const WORD_TONE = {
  cheapest: 'success',
  no_cost: 'success',
  fastest: 'success',
  keeps_ownership: 'success',
  lowers_floor_risk: 'success',
  floor_risk_unchanged: 'neutral',
  changes_timing: 'neutral',
  costs_profit_share: 'warning',
  gives_up_ownership: 'warning',
  raises_floor_risk: 'warning',
} as const
type Word = keyof typeof WORD_TONE
const isWord = (w: string): w is Word => w in WORD_TONE

export default function FundingOptions({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'funding_options'>>) {
  const { t } = useTranslation()
  const [on, setOn] = useState<Record<string, boolean>>(() => Object.fromEntries(payload.options.map((o) => [o.id, !!o.on])))
  const off = disabled || readOnly
  return (
    <WidgetCard label={t('w.funding_options.title')} title={t('w.funding_options.title')} busy={busy} disabled={disabled}>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-warning-soft/60 p-3">
            <p className="text-xs text-muted">{t('w.funding_options.gap')}</p>
            <p className="text-lg font-semibold">
              <Fig widget={widget} id={payload.gap} />
            </p>
          </div>
          <div className="rounded-xl bg-accent-soft/60 p-3">
            <p className="text-xs text-muted">{t('w.funding_options.spare')}</p>
            <p className="text-lg font-semibold">
              <Fig widget={widget} id={payload.spare} />
            </p>
          </div>
        </div>
        <div className="flex gap-3 rounded-xl bg-surface-2 p-3 text-sm">
          <Landmark aria-hidden className="mt-0.5 size-5 shrink-0 text-accent" />
          <div>
            <p className="font-medium">{t('w.funding_options.webankRole')}</p>
            <p className="text-muted">{payload.webank_role}</p>
          </div>
        </div>
        {(payload.bank_cards?.length ?? 0) > 0 && (
          <ReadOnlyCards widget={widget} cards={payload.bank_cards!} title={t('w.funding_options.banks')} note={t('w.funding_options.banksNote')} />
        )}
        {payload.options.some((o) => o.why) && <p className="text-xs text-muted">{t('w.funding_options.rankNote')}</p>}
        {payload.options.length === 0 ? (
          <EmptyState>{t('w.funding_options.empty')}</EmptyState>
        ) : (
          <ul className="flex flex-col gap-3">
            {payload.options.map((o) => {
              const closed = o.status === 'closed'
              const switchId = `fo-${widget.id}-${o.id}`
              const head = (
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <label htmlFor={switchId} className="font-semibold">
                      {o.label}
                    </label>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                      <Badge tone={STATUS_TONE[o.status]}>{t(`w.funding_options.status.${o.status}`)}</Badge>
                      {o.amount && (
                        <span className="text-sm font-medium">
                          <Fig widget={widget} id={o.amount} />
                        </span>
                      )}
                      <Words words={o.words} />
                      {o.status === 'optional' && (
                        <CollapsibleTrigger
                          className="group inline-flex min-h-8 items-center gap-0.5 rounded-md text-sm text-accent focus-visible:outline-2 focus-visible:outline-focus"
                          aria-label={t('w.funding_options.detailsFor', { option: o.label })}
                        >
                          {t('w.funding_options.details')}
                          <ChevronDown aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
                        </CollapsibleTrigger>
                      )}
                    </div>
                  </div>
                  {!readOnly && (
                    <Switch
                      id={switchId}
                      checked={!!on[o.id] && !closed}
                      disabled={off || closed}
                      onCheckedChange={(v) => {
                        setOn((s) => ({ ...s, [o.id]: v }))
                        emit('toggle_option', {
                          value: v,
                          data: { id: o.id, on: v },
                          label: t(v ? 'w.funding_options.includeLabel' : 'w.funding_options.excludeLabel', { option: o.label }),
                        })
                      }}
                    />
                  )}
                </div>
              )
              const cls = cn('rounded-xl border p-3', on[o.id] && !closed ? 'border-accent' : 'border-border', closed && 'opacity-70')
              // Optional routes start as a compact row; open (and closed) ones show their details.
              return o.status === 'optional' ? (
                <Collapsible asChild key={o.id}>
                  <li className={cls}>
                    {head}
                    <CollapsibleContent>
                      <OptionDetails option={o} />
                      <RankDetails widget={widget} option={o} />
                    </CollapsibleContent>
                  </li>
                </Collapsible>
              ) : (
                <li key={o.id} className={cls}>
                  {head}
                  <OptionDetails option={o} />
                  <RankDetails widget={widget} option={o} />
                </li>
              )
            })}
          </ul>
        )}
        {(payload.not_yet?.length ?? 0) > 0 && <NotYet cards={payload.not_yet!} />}
        {(payload.later_cards?.length ?? 0) > 0 && (
          <ReadOnlyCards widget={widget} cards={payload.later_cards!} title={t('w.funding_options.later')} note={t('w.funding_options.laterNote')} />
        )}
      </div>
    </WidgetCard>
  )
}

const VARIANT_KEY = { plan: 'webank', webank: 'webank', partner_bank: 'partner_bank', after_opening: 'after_opening' } as const

/** WeBank / registering-bank cards and the after-opening view: read-only, never switched into the plan. */
function ReadOnlyCards({
  widget,
  cards,
  title,
  note,
}: {
  widget: WidgetProps<PayloadOf<'funding_options'>>['widget']
  cards: FundingCard[]
  title: string
  note: string
}) {
  const { t } = useTranslation()
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <h4 className="text-sm font-medium">{title}</h4>
      <p className="text-xs text-muted">{note}</p>
      <ul className="flex flex-col gap-3">
        {cards.map((o) => (
          <li key={o.id} data-variant={o.variant} className="rounded-xl border border-accent/40 bg-accent-soft/30 p-3">
            <div className="flex items-start gap-2">
              <Landmark aria-hidden className="mt-0.5 size-5 shrink-0 text-accent" />
              <div className="min-w-0">
                <p className="font-semibold">{o.label}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Badge tone="accent">{t(`w.funding_options.variant.${VARIANT_KEY[o.variant ?? 'plan']}`)}</Badge>
                  <Badge tone="neutral">{t('w.funding_options.notInPlan')}</Badge>
                  {o.amount && (
                    <span className="text-sm font-medium">
                      <Fig widget={widget} id={o.amount} />
                    </span>
                  )}
                </div>
              </div>
            </div>
            <OptionDetails option={o} />
            {o.note && (
              <div className="mt-2 rounded-lg bg-warning-soft/60 px-3 py-2 text-sm">
                {o.note_rule && <p className="text-xs text-faint">{t('w.rule_card.rule', { rule: o.note_rule })}</p>}
                <p>{o.note}</p>
              </div>
            )}
            <p className="mt-2 text-xs text-faint">
              {o.as_of && t('w.funding_options.asOf', { date: o.as_of })}
              {o.as_of && o.subject_to_approval && ' · '}
              {o.subject_to_approval && t('w.funding_options.subjectToApproval')}
              {o.product?.url && (
                <>
                  {' · '}
                  <a href={o.product.url} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted underline-offset-2 hover:text-text">
                    {o.product.label || t('w.funding_options.product')}
                  </a>
                </>
              )}
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Words({ words }: { words?: string[] }) {
  const { t } = useTranslation()
  const known = (words ?? []).filter(isWord)
  if (!known.length) return null
  return (
    <>
      {known.map((w) => (
        <Badge key={w} tone={WORD_TONE[w]} data-word={w}>
          {t(`w.funding_options.word.${w}`)}
        </Badge>
      ))}
    </>
  )
}

/** The measure behind each ranking word, in the order the ranking compares them: never a score. */
function RankDetails({ widget, option: o }: { widget: WidgetProps<PayloadOf<'funding_options'>>['widget']; option: FundingCard }) {
  const { t } = useTranslation()
  if (!o.why) return null
  const rows: ['cost' | 'weeks' | 'dilution' | 'floor_change', string | null | undefined][] = [
    ['cost', o.why.cost],
    ['weeks', o.why.weeks],
    ['dilution', o.why.dilution],
    ['floor_change', o.why.floor_change],
  ]
  return (
    <section aria-label={t('w.funding_options.whyOrder')} className="mt-2 rounded-lg bg-surface-2 px-3 py-2">
      <p className="text-xs font-medium text-muted">{t('w.funding_options.whyOrder')}</p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([k, id]) =>
          id ? (
            <div key={k} className="contents">
              <dt className="text-muted">{t(`w.funding_options.measure.${k}`)}</dt>
              <dd>
                <Fig widget={widget} id={id} />
              </dd>
            </div>
          ) : null,
        )}
      </dl>
    </section>
  )
}

/** Plan routes not open to this owner yet: no switch, just what would open each one. */
function NotYet({ cards }: { cards: FundingCard[] }) {
  const { t } = useTranslation()
  return (
    <section aria-label={t('w.funding_options.notYet')} className="flex flex-col gap-2">
      <h4 className="text-sm font-medium">{t('w.funding_options.notYet')}</h4>
      <ul className="flex flex-col gap-2">
        {cards.map((o) => (
          <li key={o.id} data-not-yet={o.id} className="rounded-xl border border-dashed border-border p-3 text-sm">
            <p className="font-medium">{o.label}</p>
            {o.why_not && <p className="text-muted">{o.why_not}</p>}
          </li>
        ))}
      </ul>
    </section>
  )
}

function OptionDetails({ option: o }: { option: FundingCard }) {
  const { t } = useTranslation()
  return (
    <>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t('w.funding_options.covers')}</dt>
        <dd>{o.covers}</dd>
        <dt className="text-muted">{t('w.funding_options.when')}</dt>
        <dd>{o.available_from}</dd>
        <dt className="text-muted">{t('w.funding_options.cost')}</dt>
        <dd>{o.cost}</dd>
        <dt className="text-muted">{t('w.funding_options.conditions')}</dt>
        <dd>{o.conditions}</dd>
      </dl>
      {(o.rule_ids?.length ?? 0) > 0 && <p className="mt-2 text-xs text-faint">{t('w.funding_options.rules', { rules: o.rule_ids!.join(', ') })}</p>}
      {o.source && <SourceLine source={o.source} className="mt-1" />}
    </>
  )
}
