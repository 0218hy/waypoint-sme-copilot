import { ChevronDown, Flag } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Fig } from '@/components/Fig'
import { useFigLabel } from '@/components/figLabel'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function GoalSummary({ payload, widget, disabled, busy }: WidgetProps<PayloadOf<'goal_summary'>>) {
  const { t } = useTranslation()
  const figLabel = useFigLabel()
  return (
    <WidgetCard
      label={t('w.goal_summary.title')}
      title={
        <span className="inline-flex items-center gap-2">
          <Flag aria-hidden className="size-5 text-accent" />
          {t('w.goal_summary.title')}
        </span>
      }
      busy={busy}
      disabled={disabled}
    >
      <p className="text-[17px] leading-relaxed font-medium">{payload.sentence}</p>
      {payload.figures.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-2">
          {payload.figures.map((id) => (
            <div key={id} className="rounded-xl bg-surface-2 px-3 py-2">
              <dt className="text-xs text-muted">{figLabel(widget, id)}</dt>
              <dd className="font-semibold">
                <Fig widget={widget} id={id} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      {payload.assumptions.length > 0 && (
        <Collapsible className="mt-3">
          <CollapsibleTrigger className="group inline-flex min-h-9 items-center gap-1 text-sm text-accent focus-visible:outline-2 focus-visible:outline-focus">
            {t('w.goal_summary.assumptions')}
            <ChevronDown aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-1 list-disc pl-5 text-sm text-muted">
              {payload.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      )}
    </WidgetCard>
  )
}
