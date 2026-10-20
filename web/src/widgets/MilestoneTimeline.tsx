import { Check, CheckCircle2, ChevronRight, Circle, Clock, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

const STATUS_TONE = { upcoming: 'neutral', due: 'warning', done: 'success', late: 'danger' } as const

export default function MilestoneTimeline({ payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'milestone_timeline'>>) {
  const { t } = useTranslation()
  const items = [...payload.items].sort((a, b) => a.order - b.order)
  const off = disabled || readOnly
  return (
    <WidgetCard
      label={t('w.milestone_timeline.title')}
      title={t('w.milestone_timeline.title')}
      subtitle={t('w.milestone_timeline.start', { date: payload.start_date })}
      busy={busy}
      disabled={disabled}
    >
      {items.length === 0 ? (
        <EmptyState>{t('w.milestone_timeline.empty')}</EmptyState>
      ) : (
        <ol className="relative flex flex-col">
          {items.map((m, i) => {
            const status = m.status ?? 'upcoming'
            const last = i === items.length - 1
            const Icon = status === 'done' ? CheckCircle2 : status === 'due' || status === 'late' ? Clock : Circle
            const body = (
              <>
                <div className="flex items-start justify-between gap-2">
                  <p className={cn('font-medium leading-snug', status === 'done' && 'text-muted line-through decoration-1')}>{m.label}</p>
                  {status !== 'upcoming' && <Badge tone={STATUS_TONE[status]}>{t(`w.milestone_timeline.status.${status}`)}</Badge>}
                </div>
                <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted">
                  <User aria-hidden className="size-3" />
                  {m.who}
                </p>
                <dl className="mt-1.5 grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <dt className="text-faint">{t('w.milestone_timeline.likely')}</dt>
                    <dd className="font-medium">{m.likely_date}</dd>
                  </div>
                  <div>
                    <dt className="text-faint">{t('w.milestone_timeline.latestSafe')}</dt>
                    <dd className="font-medium">{m.latest_safe_date}</dd>
                  </div>
                  <div>
                    <dt className="text-faint">{t('w.milestone_timeline.actBy')}</dt>
                    <dd className={cn('font-medium', (status === 'due' || status === 'late') && 'text-warning')}>{m.act_by_date}</dd>
                  </div>
                </dl>
                {m.done_date && <p className="mt-1 text-xs text-success">{t('w.milestone_timeline.doneOn', { date: m.done_date })}</p>}
                {m.detail && <p className="mt-1 text-xs text-muted">{m.detail}</p>}
              </>
            )
            return (
              <li key={m.id} className="relative flex gap-3 pb-4 last:pb-0">
                {!last && <span aria-hidden className="absolute top-7 bottom-0 left-[13px] w-0.5 bg-border" />}
                <span className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full bg-surface">
                  <Icon
                    aria-hidden
                    className={cn(
                      'size-6',
                      status === 'done' ? 'text-success' : status === 'late' ? 'text-danger' : status === 'due' ? 'text-warning' : 'text-faint',
                    )}
                  />
                </span>
                {readOnly ? (
                  <div className="min-w-0 flex-1">{body}</div>
                ) : (
                  <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    disabled={off}
                    onClick={() => emit('open_milestone', { value: m.id, data: { id: m.id }, label: m.label })}
                    className="group min-w-0 flex-1 rounded-xl p-2 -m-2 text-left hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-focus disabled:hover:bg-transparent"
                    aria-label={t('w.milestone_timeline.open', { label: m.label })}
                  >
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">{body}</div>
                      <ChevronRight aria-hidden className="mt-1 size-4 shrink-0 text-faint group-disabled:hidden" />
                    </div>
                  </button>
                  {m.can_mark_done && status !== 'done' && (
                    <Button
                      variant="soft"
                      size="sm"
                      className="mt-2"
                      disabled={off}
                      onClick={() => emit('mark_milestone_done', { value: m.id, data: { id: m.id }, label: t('w.milestone_timeline.markedLabel', { label: m.label }) })}
                      aria-label={t('w.milestone_timeline.markDoneAria', { label: m.label })}
                    >
                      <Check aria-hidden />
                      {m.money_step ? t('w.milestone_timeline.markDoneMoney') : t('w.milestone_timeline.markDone')}
                    </Button>
                  )}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </WidgetCard>
  )
}
