import { MapPin } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MapArea } from '@/contracts/types'
import { EChart } from '@/charts/EChart'
import { useChartTheme } from '@/charts/theme'
import { ErrorState } from '@/components/ErrorState'
import { SourceLine } from '@/components/Fig'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import { useJson } from '@/lib/useJson'
import { useWidgetEnv } from './env'
import { useWidgetLayout } from './layout'
import type { PayloadOf, WidgetProps } from './types'

const MAP_NAME = 'wp_planning_areas'

type Ring = [number, number][]
interface Feature {
  type: 'Feature'
  properties: Record<string, unknown> | null
  geometry: { type: 'Polygon'; coordinates: Ring[] } | { type: 'MultiPolygon'; coordinates: Ring[][] } | null
}
interface FeatureCollection {
  type: 'FeatureCollection'
  features: Feature[]
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9一-鿿]/g, '')

/**
 * Tag each GeoJSON feature with the matching area id (by any string property equal to the
 * area's id or name), so the map can key data by area id whatever the property is called.
 */
function prepare(geo: FeatureCollection, areas: MapArea[]) {
  const byKey = new Map<string, string>()
  for (const a of areas) {
    byKey.set(norm(a.id), a.id)
    byKey.set(norm(a.name), a.id)
  }
  const centroids = new Map<string, [number, number]>()
  const features = geo.features.map((f, i) => {
    const props = f.properties ?? {}
    let id: string | undefined
    for (const v of Object.values(props)) {
      if (typeof v === 'string' && byKey.has(norm(v))) {
        id = byKey.get(norm(v))
        break
      }
    }
    const key = id ?? `__unmatched_${i}`
    if (id && f.geometry) centroids.set(id, centroid(f.geometry))
    return { ...f, properties: { ...props, __wp: key } }
  })
  return { geo: { ...geo, features }, centroids }
}

function centroid(g: NonNullable<Feature['geometry']>): [number, number] {
  const rings = g.type === 'Polygon' ? [g.coordinates[0]] : g.coordinates.map((p) => p[0])
  // Largest ring by bounding-box area, then its vertex mean: good enough to place a pin.
  let best: Ring = rings[0] ?? []
  let bestArea = -1
  for (const r of rings) {
    const xs = r.map((p) => p[0])
    const ys = r.map((p) => p[1])
    const a = (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys))
    if (a > bestArea) {
      bestArea = a
      best = r
    }
  }
  const n = best.length || 1
  return [best.reduce((s, p) => s + p[0], 0) / n, best.reduce((s, p) => s + p[1], 0) / n]
}

export default function AreaMap({ payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'area_map'>>) {
  const { t, i18n } = useTranslation()
  const env = useWidgetEnv()
  const theme = useChartTheme()
  const mapHeight = useWidgetLayout() === 'canvas' ? 440 : 260
  const [geoState, retry] = useJson<FeatureCollection>(env.resolveUrl(payload.geojson_url))
  const [selected, setSelected] = useState<string | null>(null)
  const off = disabled || readOnly
  const areasById = useMemo(() => new Map(payload.areas.map((a) => [a.id, a])), [payload.areas])
  const top = payload.top.map((id) => areasById.get(id)).filter((a): a is MapArea => !!a)

  const prepared = useMemo(
    () => (geoState.status === 'ready' ? prepare(geoState.data, payload.areas) : null),
    [geoState, payload.areas],
  )

  const pick = (id: string) => {
    if (off) return
    const a = areasById.get(id)
    if (!a) return
    setSelected(id)
    emit('select_area', { value: id, data: { id }, label: a.name })
  }

  const option = useMemo(() => {
    if (!prepared) return null
    const pins = top
      .map((a, i) => {
        const c = prepared.centroids.get(a.id)
        return c ? { name: a.id, value: [...c, i + 1], label: `${i + 1}. ${a.name}` } : null
      })
      .filter((p) => p !== null)
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: { name: string; value?: number }) => {
          const a = areasById.get(p.name)
          if (!a) return ''
          return a.score != null ? `${a.name}<br/>${t('w.area_map.match')}: ${Math.round(a.score)}/100` : a.name
        },
      },
      visualMap: {
        type: 'continuous',
        // Stretch the colour ramp over the scores present so differences stay visible.
        min: Math.max(0, Math.floor(Math.min(...payload.areas.map((a) => a.score ?? 100))) - 5),
        max: Math.min(100, Math.ceil(Math.max(...payload.areas.map((a) => a.score ?? 0))) + 2),
        show: false,
        inRange: { color: [theme.grid, theme.accent] },
        // Areas without a score (no residents, water, industry) stay neutral, never the default blue.
        outOfRange: { color: [theme.grid] },
        seriesIndex: 0,
      },
      geo: {
        map: MAP_NAME,
        nameProperty: '__wp',
        roam: true,
        scaleLimit: { min: 1, max: 6 },
        itemStyle: { areaColor: theme.grid, borderColor: theme.surface, borderWidth: 0.8 },
        emphasis: { itemStyle: { areaColor: theme.band }, label: { show: false } },
        select: { disabled: true },
        label: { show: false },
      },
      series: [
        {
          type: 'map',
          geoIndex: 0,
          itemStyle: { areaColor: theme.grid, color: theme.grid },
          // Every planning area is listed; unscored ones get an explicit neutral colour.
          data: [...prepared.centroids.keys()].map((id) => {
            const a = areasById.get(id)
            return a?.score != null
              ? { name: id, value: a.score }
              : { name: id, value: NaN, itemStyle: { areaColor: theme.grid, color: theme.grid } }
          }),
        },
        {
          type: 'scatter',
          coordinateSystem: 'geo',
          symbol: 'pin',
          symbolSize: 34,
          itemStyle: { color: theme.text },
          label: { show: true, formatter: (p: { value: number[] }) => String(p.value[2]), color: theme.surface, fontWeight: 700, offset: [0, -3] },
          data: pins,
          z: 5,
        },
        {
          type: 'scatter',
          coordinateSystem: 'geo',
          symbolSize: 0,
          label: {
            show: true,
            position: 'bottom',
            distance: 4,
            formatter: (p: { name: string }) => areasById.get(p.name)?.name ?? '',
            color: theme.text,
            fontSize: 12,
            fontWeight: 600,
            textBorderColor: theme.surface,
            textBorderWidth: 3,
          },
          data: pins,
          silent: true,
          z: 6,
        },
      ],
    }
  }, [prepared, top, areasById, payload.areas, theme, t])

  const sortedAreas = useMemo(
    () => [...payload.areas].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999) || a.name.localeCompare(b.name, i18n.language)),
    [payload.areas, i18n.language],
  )

  return (
    <WidgetCard label={t('w.area_map.title')} title={t('w.area_map.title')} subtitle={t('w.area_map.subtitle')} busy={busy} disabled={disabled}>
      {payload.areas.length === 0 ? (
        <EmptyState>{t('w.area_map.empty')}</EmptyState>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="-mx-2 overflow-hidden rounded-xl bg-surface-2">
            {geoState.status === 'loading' && <Skeleton className="w-full" height={mapHeight} />}
            {geoState.status === 'error' && (
              <div className="p-3">
                <ErrorState message={t('w.area_map.mapError')} onRetry={retry} />
              </div>
            )}
            {option && (
              <EChart
                option={option}
                maps={{ [MAP_NAME]: prepared!.geo }}
                height={mapHeight}
                label={t('w.area_map.chartLabel', { areas: top.map((a) => a.name).join(', ') })}
                onEvents={{
                  click: (p) => {
                    const name = (p as { name?: string }).name
                    if (name) pick(name)
                  },
                }}
              />
            )}
          </div>

          <ol className="flex flex-col gap-3" aria-label={t('w.area_map.topList')}>
            {top.map((a, i) => (
              <li
                key={a.id}
                className={cn('rounded-xl border p-3', selected === a.id ? 'border-accent bg-accent-soft' : 'border-border')}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-text text-sm font-bold text-surface">{i + 1}</span>
                    <span className="font-semibold">{a.name}</span>
                  </div>
                  {a.score != null && <ScoreMeter score={a.score} />}
                </div>
                {(payload.reasons[a.id]?.length ?? 0) > 0 && (
                  <ul className="mt-2 flex list-disc flex-col gap-0.5 pl-6 text-sm text-muted">
                    {payload.reasons[a.id]!.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
                {!readOnly && (
                  <Button size="sm" variant={selected === a.id ? 'primary' : 'secondary'} className="mt-2" disabled={off} onClick={() => pick(a.id)}>
                    <MapPin aria-hidden />
                    {t('w.area_map.see', { name: a.name })}
                  </Button>
                )}
              </li>
            ))}
          </ol>

          {!readOnly && sortedAreas.length > top.length && (
            <div className="flex flex-col gap-1">
              <label htmlFor="area-other" className="text-sm text-muted">
                {t('w.area_map.other')}
              </label>
              <select
                id="area-other"
                disabled={off}
                value=""
                onChange={(e) => e.target.value && pick(e.target.value)}
                className="min-h-11 rounded-xl border border-border-strong bg-surface px-3 text-[15px] focus-visible:outline-2 focus-visible:outline-focus"
              >
                <option value="">{t('w.area_map.otherPlaceholder')}</option>
                {sortedAreas
                  .filter((a) => !payload.top.includes(a.id))
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                      {a.score != null ? ` (${Math.round(a.score)})` : ''}
                    </option>
                  ))}
              </select>
            </div>
          )}

          {payload.sources.length > 0 && (
            <div className="flex flex-col gap-0.5">
              {payload.sources.map((s) => (
                <SourceLine key={s.label} source={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </WidgetCard>
  )
}

function ScoreMeter({ score }: { score: number }) {
  const { t } = useTranslation()
  const v = Math.max(0, Math.min(100, Math.round(score)))
  return (
    <div className="flex items-center gap-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={v} aria-label={t('w.area_map.match')}>
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-surface-3">
        <div className="h-full rounded-full bg-accent" style={{ width: `${v}%` }} />
      </div>
      <span className="tabular text-xs text-muted">{v}</span>
    </div>
  )
}
