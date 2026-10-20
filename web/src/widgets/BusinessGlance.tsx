import { Activity, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RatioRow, Widget } from '@/contracts/types'
import { Fig } from '@/components/Fig'
import { Badge } from '@/components/ui/badge'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

/** "Your business at a glance": ratios worked out from the feed (tools/ratios.py). Display only. */
export default function BusinessGlance({ payload, widget, disabled, busy }: WidgetProps<PayloadOf<'business_glance'>>) {
  const { t } = useTranslation()
  const sg = payload.singapore ?? []
  return (
    <WidgetCard
      label={t('w.business_glance.title')}
      title={
        <span className="inline-flex items-center gap-2">
          <Activity aria-hidden className="size-5 text-accent" />
          {t('w.business_glance.title')}
        </span>
      }
      subtitle={payload.note ?? undefined}
      aside={payload.simulated_feed !== false ? <Badge tone="warning">{t('common.simulated')}</Badge> : undefined}
      busy={busy}
      disabled={disabled}
    >
      {payload.rows.length === 0 ? (
        <EmptyState>{t('w.business_glance.empty')}</EmptyState>
      ) : (
        <div className="flex flex-col gap-4">
          <Rows rows={payload.rows} widget={widget} />
          {sg.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-faint">{t('w.business_glance.singapore')}</p>
              <Rows rows={sg} widget={widget} />
            </div>
          )}
          <p className="text-xs text-muted">{t('w.business_glance.asOf', { date: payload.as_of })}</p>
        </div>
      )}
    </WidgetCard>
  )
}

function Rows({ rows, widget }: { rows: RatioRow[]; widget: Widget }) {
  return (
    <dl className="flex flex-col divide-y divide-border">
      {rows.map((r) => (
        <div key={r.key} className="flex flex-col gap-0.5 py-2 first:pt-0">
          <div className="flex items-start justify-between gap-3 text-sm">
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
          {r.note && (
            <p className={cn('text-xs', r.caveat ? 'inline-flex items-start gap-1 text-warning' : 'text-faint')}>
              {r.caveat && <TriangleAlert aria-hidden className="mt-0.5 size-3 shrink-0" />}
              {r.note}
            </p>
          )}
        </div>
      ))}
    </dl>
  )
}
