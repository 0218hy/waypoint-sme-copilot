import { Check } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Fig } from '@/components/Fig'
import { Button } from '@/components/ui/button'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

export default function RepairOptions({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'repair_options'>>) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState<string | null>(null)
  const off = disabled || readOnly || picked !== null
  return (
    <WidgetCard label={t('w.repair_options.title')} title={t('w.repair_options.title')} subtitle={t('w.repair_options.subtitle')} busy={busy} disabled={disabled}>
      {payload.repairs.length === 0 ? (
        <EmptyState>{t('w.repair_options.empty')}</EmptyState>
      ) : (
        <ul className="flex flex-col gap-3">
          {payload.repairs.map((r) => (
            <li key={r.id} className={cn('rounded-xl border p-3', picked === r.id ? 'border-accent bg-accent-soft/50' : 'border-border')}>
              <p className="font-semibold">{r.label}</p>
              <p className="text-sm text-muted">{r.detail}</p>
              <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <dt className="text-faint">{t('w.repair_options.likely')}</dt>
                  <dd className="text-sm font-medium"><Fig widget={widget} id={r.new_open_likely} /></dd>
                </div>
                <div>
                  <dt className="text-faint">{t('w.repair_options.bad')}</dt>
                  <dd className="text-sm font-medium"><Fig widget={widget} id={r.new_open_p95} /></dd>
                </div>
                <div>
                  <dt className="text-faint">{t('w.repair_options.floorRisk')}</dt>
                  <dd className="text-sm font-medium"><Fig widget={widget} id={r.new_floor_risk} /></dd>
                </div>
              </dl>
              {!readOnly && (
                <Button
                  size="sm"
                  className="mt-2"
                  variant={picked === r.id ? 'primary' : 'secondary'}
                  disabled={off}
                  onClick={() => {
                    setPicked(r.id)
                    emit('select_repair', { value: r.id, data: { id: r.id, alert_id: payload.alert_id }, label: r.label })
                  }}
                >
                  {picked === r.id && <Check aria-hidden />}
                  {t('w.repair_options.pick')}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}
