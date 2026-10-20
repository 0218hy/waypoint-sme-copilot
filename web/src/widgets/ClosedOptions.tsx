import { ChevronDown, Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SourceLine } from '@/components/Fig'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { PayloadOf, WidgetProps } from './types'

export default function ClosedOptions({ payload }: WidgetProps<PayloadOf<'closed_options'>>) {
  const { t } = useTranslation()
  if (payload.options.length === 0) return null
  return (
    <Card role="group" aria-label={t('w.closed_options.title')}>
      <Collapsible>
        <CollapsibleTrigger className="group flex min-h-12 w-full items-center gap-2 px-4 py-3 text-left font-medium focus-visible:outline-2 focus-visible:outline-focus">
          <Lock aria-hidden className="size-4 text-muted" />
          <span className="flex-1">{t('w.closed_options.title')}</span>
          <ChevronDown aria-hidden className="size-4 text-muted transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="flex flex-col gap-3 px-4 pb-4">
            {payload.options.map((o) => (
              <li key={o.id} className="rounded-xl bg-surface-2 p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium">{o.label}</p>
                  <Badge tone="danger">{t('w.closed_options.closed')}</Badge>
                </div>
                <p className="mt-1 text-sm">{o.reason}</p>
                <p className="mt-1 text-xs text-faint">{t('w.closed_options.rule', { rule: o.rule_id })}</p>
                <SourceLine source={o.source} className="mt-1" />
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
