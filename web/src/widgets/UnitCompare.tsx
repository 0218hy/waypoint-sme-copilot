import { Check, Map as MapIcon } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { UnitRow, Widget } from '@/contracts/types'
import { Fig } from '@/components/Fig'
import { figValue } from '@/components/figValues'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

const UnitMap = lazy(() => import('@/components/UnitMap'))

export default function UnitCompare({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'unit_compare'>>) {
  const { t } = useTranslation()
  const [chosen, setChosen] = useState<string | null>(payload.chosen ?? null)
  const [showMap, setShowMap] = useState(false)
  const off = disabled || readOnly
  const pins = payload.units
    .filter((u) => u.lat != null && u.lng != null)
    .map((u) => ({ id: u.id, lat: u.lat!, lng: u.lng!, label: `${u.mall} ${u.unit_no}`, chosen: u.id === chosen }))
  return (
    <WidgetCard
      label={t('w.unit_compare.title')}
      title={t('w.unit_compare.title')}
      subtitle={t('w.unit_compare.subtitle')}
      busy={busy}
      disabled={disabled}
    >
      {payload.units.length === 0 ? (
        <EmptyState>{t('w.unit_compare.empty')}</EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          <ul className={cn('grid grid-cols-1 gap-3', payload.units.length === 2 ? '@md:grid-cols-2' : '@md:grid-cols-2 @3xl:grid-cols-3')}>
            {payload.units.map((u) => (
              <UnitCardView
                key={u.id}
                unit={u}
                widget={widget}
                chosen={chosen === u.id}
                off={off}
                readOnly={readOnly}
                onPick={() => {
                  setChosen(u.id)
                  emit('select_unit', { value: u.id, data: { id: u.id }, label: t('w.unit_compare.pickLabel', { mall: u.mall, unit: u.unit_no }) })
                }}
              />
            ))}
          </ul>
          {pins.length > 0 &&
            (showMap ? (
              <Suspense fallback={<Skeleton className="h-[220px] w-full" />}>
                <UnitMap pins={pins} label={t('w.unit_compare.mapLabel')} />
              </Suspense>
            ) : (
              <Button variant="ghost" size="sm" className="self-start" onClick={() => setShowMap(true)}>
                <MapIcon aria-hidden />
                {t('w.unit_compare.showMap')}
              </Button>
            ))}
        </div>
      )}
    </WidgetCard>
  )
}

function UnitCardView({
  unit: u,
  widget,
  chosen,
  off,
  readOnly,
  onPick,
}: {
  unit: UnitRow
  widget: Widget
  chosen: boolean
  off: boolean
  readOnly: boolean
  onPick: () => void
}) {
  const { t, i18n } = useTranslation()
  const be = figValue(widget, u.breakeven)
  const best = figValue(widget, u.best_shop_cups)
  const avg = figValue(widget, u.avg_shop_cups)
  const scale = Math.max(be ?? 0, best ?? 0, avg ?? 0) || 1
  const size = new Intl.NumberFormat(i18n.language === 'zh' ? 'zh-CN' : 'en-SG').format(u.size_sqft)
  return (
    <li className={cn('flex flex-col gap-3 rounded-xl border p-3', chosen ? 'border-accent bg-accent-soft/50 ring-1 ring-accent' : 'border-border')}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold leading-snug">{u.mall}</p>
          <p className="text-sm text-muted">
            {u.unit_no} · {u.area_name}
          </p>
        </div>
        {u.simulated !== false && <Badge tone="warning">{t('common.simulated')}</Badge>}
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
        <dt className="text-muted">{t('w.unit_compare.size')}</dt>
        <dd className="tabular text-right">{t('w.unit_compare.sqft', { size })}</dd>
        <dt className="text-muted">{t('w.unit_compare.rent')}</dt>
        <dd className="text-right font-medium">
          <Fig widget={widget} id={u.rent} />
        </dd>
        <dt className="text-muted">{t('w.unit_compare.gto')}</dt>
        <dd className="text-right">{u.gto_pct != null ? t('w.unit_compare.gtoValue', { pct: Math.round(u.gto_pct * 1000) / 10 }) : t('w.unit_compare.noGto')}</dd>
        <dt className="text-muted">{t('w.unit_compare.early')}</dt>
        <dd className="text-right font-medium">
          <Fig widget={widget} id={u.early_cost} />
        </dd>
      </dl>
      <div className="flex flex-col gap-1.5" aria-label={t('w.unit_compare.breakeven')} role="group">
        <p className="text-sm font-medium">{t('w.unit_compare.breakeven')}</p>
        <Bar fraction={be != null ? be / scale : 0} tone="accent">
          <span>{t('w.unit_compare.needs')}</span> <Fig widget={widget} id={u.breakeven} />
        </Bar>
        {u.best_shop_cups && (
          <Bar fraction={best != null ? best / scale : 0} tone="muted">
            <span>{t('w.unit_compare.bestShop')}</span> <Fig widget={widget} id={u.best_shop_cups} />
          </Bar>
        )}
        {u.avg_shop_cups && (
          <Bar fraction={avg != null ? avg / scale : 0} tone="muted">
            <span>{t('w.unit_compare.avgShop')}</span> <Fig widget={widget} id={u.avg_shop_cups} />
          </Bar>
        )}
      </div>
      {!readOnly && (
        <Button variant={chosen ? 'primary' : 'secondary'} disabled={off} onClick={onPick} aria-pressed={chosen} className="mt-auto">
          {chosen && <Check aria-hidden />}
          {chosen ? t('w.unit_compare.picked') : t('w.unit_compare.pick')}
        </Button>
      )}
    </li>
  )
}

function Bar({ fraction, tone, children }: { fraction: number; tone: 'accent' | 'muted'; children: React.ReactNode }) {
  return (
    <div>
      <div className="h-2.5 overflow-hidden rounded-full bg-surface-3" aria-hidden>
        <div
          className={cn('h-full rounded-full', tone === 'accent' ? 'bg-accent' : 'bg-faint')}
          style={{ width: `${Math.max(2, Math.min(1, fraction) * 100)}%` }}
        />
      </div>
      <p className="mt-0.5 text-xs text-muted">{children}</p>
    </div>
  )
}
