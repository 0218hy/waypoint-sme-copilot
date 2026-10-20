import { CalendarClock, FileText, Flag, MessageSquare } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/contracts/types'
import { useOptionalChat } from '@/chat/chatContext'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { useApi } from '@/lib/useApi'
import { LG, useMediaQuery } from '@/lib/useMediaQuery'
import type { Emit } from '@/widgets/types'
import { WidgetView } from '@/widgets/WidgetView'

/** SPEC §7.3 order: header, savings, next step, timeline, your plan, alerts and history. */
const ORDER = ['status_card', 'plan_vs_actual', 'milestone_timeline', 'plan_summary', 'business_glance', 'unit_economics', 'cost_breakdown', 'funding_mix', 'alert_card'] as const
const PLAN_ORDER = { site: 0, cost: 1, funding: 2 } as const

function rank(w: Widget): number {
  const i = ORDER.indexOf(w.payload.type as (typeof ORDER)[number])
  const base = (i < 0 ? ORDER.length : i) * 10
  return w.payload.type === 'plan_summary' ? base + PLAN_ORDER[w.payload.kind] : base
}

export function GoalTab({ onOpenChat }: { onOpenChat: () => void }) {
  const { t } = useTranslation()
  const chat = useOptionalChat()
  const [state, reload] = useApi(() => api.goal(), [chat?.journey?.goal_id])
  const wide = useMediaQuery(LG)
  // Demo clock moved: the weekly check may have changed the goal.
  useEffect(() => {
    window.addEventListener('waypoint:demo-advanced', reload)
    return () => window.removeEventListener('waypoint:demo-advanced', reload)
  }, [reload])

  const widgets = useMemo(() => {
    if (state.status !== 'ready') return []
    return state.data.widgets.map((w, i) => ({ w, i })).sort((a, b) => rank(a.w) - rank(b.w) || a.i - b.i).map((x) => x.w)
  }, [state])

  if (state.status === 'loading') {
    return (
      <div className="flex flex-col gap-3" aria-busy>
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-56 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (state.status === 'error') return <ErrorState message={t('goal.loadError')} onRetry={reload} />

  const { goal } = state.data
  if (!goal) {
    return (
      <Card className="flex flex-col items-start gap-3 p-5">
        <Flag aria-hidden className="size-8 text-accent" />
        <h2 className="text-lg font-semibold">{t('goal.noneTitle')}</h2>
        <p className="text-muted">{t('goal.noneBody')}</p>
        <Button onClick={onOpenChat}>
          <MessageSquare aria-hidden />
          {t('goal.resume')}
        </Button>
      </Card>
    )
  }

  const timeline = widgets.find((w) => w.payload.type === 'milestone_timeline')
  const next =
    timeline?.payload.type === 'milestone_timeline'
      ? [...timeline.payload.items].sort((a, b) => a.order - b.order).find((m) => m.status !== 'done')
      : undefined
  const nextStep = goal.next_step as { id: string; draft: 'consent_request' | 'checklist' | null } | null | undefined
  const draft = next && nextStep?.id === next.id ? nextStep.draft : null
  const changing = goal.change_in_progress === true
  const firstAlert = widgets.findIndex((w) => w.payload.type === 'alert_card')

  // In the Goal tab only "Change in chat" and an open alert's "See fixes" act; each opens the chat and
  // sends its event there.
  const emitFor =
    (w: Widget): Emit =>
    (event, { value, data, label }) => {
      onOpenChat()
      chat?.sendEvent({ widget_id: w.id, event, value: value ?? null, data: data ?? {} }, label)
    }

  const blocks = widgets.map((w, i) => ({
    w,
    // Desktop columns (SPEC §7.3): status + savings (+ alerts) left; next step, timeline and plan right.
    col: (['status_card', 'plan_vs_actual', 'alert_card'] as const).includes(w.payload.type as 'status_card') ? 'left' : 'right',
    node: (
      <div key={w.id} className="flex flex-col gap-4">
        {w === timeline && next && (
          <Card className="flex gap-3 p-4">
            <CalendarClock aria-hidden className="mt-0.5 size-5 shrink-0 text-accent" />
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-faint">{t('goal.next')}</p>
              <p className="font-semibold">{next.label}</p>
              <p className="text-sm text-muted">{t('goal.actBy', { date: next.act_by_date, who: next.who })}</p>
              {next.detail && <p className="mt-1 text-sm">{next.detail}</p>}
              {draft && (
                <Button
                  variant="soft"
                  size="sm"
                  className="mt-2"
                  onClick={() => emitFor(timeline)('open_milestone', { value: next.id, data: { id: next.id }, label: next.label })}
                >
                  <FileText aria-hidden />
                  {t(draft === 'consent_request' ? 'goal.openDraft' : 'goal.openChecklist')}
                </Button>
              )}
            </div>
          </Card>
        )}
        {w.payload.type === 'plan_summary' && w.payload.kind === 'site' && <h2 className="mt-2 text-lg font-semibold">{t('goal.yourPlan')}</h2>}
        {i === firstAlert && <h2 className="mt-2 text-lg font-semibold">{t('goal.alerts')}</h2>}
        <WidgetView name={w.payload.type ?? ''} widget={w} complete emit={emitFor(w)} readOnly={w.payload.type !== 'alert_card'} />
      </div>
    ),
  }))

  const talk = (
    <Button variant="secondary" size="lg" onClick={onOpenChat}>
      <MessageSquare aria-hidden />
      {t('goal.talk')}
    </Button>
  )

  return (
    <div className="flex flex-col gap-4">
      {changing && <p className="rounded-xl bg-info-soft px-3 py-2 text-sm">{t('goal.changing')}</p>}
      {wide ? (
        <div className="grid grid-cols-2 items-start gap-6">
          <div className="flex flex-col gap-4">
            {blocks.filter((b) => b.col === 'left').map((b) => b.node)}
            {talk}
          </div>
          <div className="flex flex-col gap-4">{blocks.filter((b) => b.col === 'right').map((b) => b.node)}</div>
        </div>
      ) : (
        <>
          {blocks.map((b) => b.node)}
          {talk}
        </>
      )}
    </div>
  )
}
