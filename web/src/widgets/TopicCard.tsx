import { BookOpen, ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SourceLine } from '@/components/Fig'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function TopicCard({ payload, busy, disabled }: WidgetProps<PayloadOf<'topic_card'>>) {
  const { t } = useTranslation()
  return (
    <WidgetCard
      label={payload.title}
      title={
        <span className="inline-flex items-start gap-2">
          <BookOpen aria-hidden className="mt-0.5 size-5 shrink-0 text-accent" />
          {payload.title}
        </span>
      }
      className="bg-info-soft/40"
      busy={busy}
      disabled={disabled}
    >
      <p className="text-[15px]">{payload.say}</p>
      {payload.more && (
        <Collapsible className="mt-2">
          <CollapsibleTrigger className="group inline-flex min-h-9 items-center gap-1 text-sm font-medium text-accent focus-visible:outline-2 focus-visible:outline-focus">
            <span className="group-data-[state=open]:hidden">{t('w.topic_card.more')}</span>
            <span className="hidden group-data-[state=open]:inline">{t('w.topic_card.less')}</span>
            <ChevronDown aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <p className="mt-1 whitespace-pre-line text-sm text-muted">{payload.more}</p>
          </CollapsibleContent>
        </Collapsible>
      )}
      <SourceLine source={payload.source} className="mt-2" />
    </WidgetCard>
  )
}
