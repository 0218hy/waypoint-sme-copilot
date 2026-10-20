// Dev-only widget gallery (#/dev/widgets): every widget rendered from a fixture, no backend needed.
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ChartSeries, Widget, WidgetEvent } from '@/contracts/types'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import type { SetasidePreview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { applyTheme, getThemePref, type ThemePref } from '@/lib/theme'
import { LanguageToggle } from '@/shell/LanguageToggle'
import { Wordmark } from '@/shell/Wordmark'
import { WidgetEnvContext, type WidgetEnv } from '@/widgets/env'
import { WidgetLayoutContext } from '@/widgets/layout'
import { WidgetView } from '@/widgets/WidgetView'
import geoUrl from './planning_areas.sample.geojson?url'
import { fixtures } from './fixtures'
import quoteUrl from './quote.sample.svg?url'


/** Dev stand-in for GET /api/preview/setaside: scales the fixture series by share. Not a model. */
function fakePreview(base: Widget, share: number): SetasidePreview {
  if (base.payload.type !== 'setaside_slider') throw new Error('not a slider')
  const p = base.payload
  const k = share / (p.share || 0.01)
  const c: ChartSeries = p.chart
  const pot = (arr: number[]) => arr.map((v, i) => Math.round(arr[0]! + (v - arr[0]!) * k + 0 * i))
  const home = (arr: number[]) => arr.map((v, i) => Math.round(v - (share - p.share) * 400000 * (i / Math.max(1, arr.length - 1))))
  const months = Math.max(8, Math.round(14 / Math.max(0.2, k)))
  const pct = Math.max(0.4, 3.1 * k * k)
  return {
    chart: { ...c, pot_p10: pot(c.pot_p10), pot_p50: pot(c.pot_p50), pot_p90: pot(c.pot_p90), home_p05: home(c.home_p05), home_p50: home(c.home_p50) },
    figures: {},
    display: {
      [p.open_likely]: `about month ${months} (dev preview)`,
      [p.open_p95]: `by month ${months + 3} (dev preview)`,
      [p.floor_risk]: `${pct.toFixed(1)}%`,
      [p.monthly_amount]: `RMB ${Math.round(420000 * share).toLocaleString('en')}`,
    },
  }
}

export default function Gallery() {
  const { t } = useTranslation()
  const [events, setEvents] = useState<{ ev: WidgetEvent; label: string; at: string }[]>([])
  const [theme, setTheme] = useState<ThemePref>(getThemePref)
  const [readOnly, setReadOnly] = useState(false)
  const [disabled, setDisabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [canvas, setCanvas] = useState(false)

  const env = useMemo<WidgetEnv>(
    () => ({
      resolveUrl: (u) => (u.includes('planning_areas') ? geoUrl : u.includes('/api/docs/') ? quoteUrl : u.replace(/^\//, '')),
      previewSetaside: (_url, share, signal) =>
        new Promise((resolve, reject) => {
          const base = fixtures.find((f) => f.widget.payload.type === 'setaside_slider')!.widget
          const id = setTimeout(() => resolve(fakePreview(base, share)), 90)
          signal.addEventListener('abort', () => {
            clearTimeout(id)
            reject(new DOMException('aborted', 'AbortError'))
          })
        }),
      // the gallery has no plan model: it answers with the fixture's own columns, unchanged
      previewCompare: (_url, _savings, signal) =>
        new Promise((resolve, reject) => {
          const base = fixtures.find((f) => f.widget.payload.type === 'funding_compare')!.widget
          const p = base.payload as { columns: import('@/contracts/types').CompareColumn[] }
          const id = setTimeout(() => resolve({ columns: p.columns, figures: base.figures, display: base.display }), 90)
          signal.addEventListener('abort', () => {
            clearTimeout(id)
            reject(new DOMException('aborted', 'AbortError'))
          })
        }),
      sampleQuote: async () => new File([await (await fetch(quoteUrl)).blob()], 'sample-quote.svg', { type: 'image/svg+xml' }),
      upload: (file) => new Promise((resolve) => setTimeout(() => resolve({ doc_id: `doc_dev_${file.name.length}` }), 600)),
      openTab: (tab) => setEvents((e) => [{ ev: { widget_id: '-', event: 'back', value: `openTab:${tab}` }, label: `(navigate to ${tab})`, at: new Date().toLocaleTimeString() }, ...e]),
    }),
    [],
  )

  return (
    <WidgetEnvContext.Provider value={env}>
      <div className="min-h-dvh pb-48">
        <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
          <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-2 px-3 py-2">
            <div className="flex items-center gap-2">
              <Wordmark />
              <span className="text-sm text-muted">{t('dev.title')}</span>
            </div>
            <LanguageToggle />
          </div>
          <div className="mx-auto flex max-w-2xl flex-wrap items-center gap-x-4 gap-y-2 px-3 pb-2 text-sm">
            <div role="radiogroup" aria-label={t('dev.theme')} className="inline-flex rounded-full bg-surface-2 p-0.5">
              {(['system', 'light', 'dark'] as const).map((v) => (
                <button
                  key={v}
                  role="radio"
                  aria-checked={theme === v}
                  onClick={() => {
                    setTheme(v)
                    applyTheme(v)
                  }}
                  className={cn('min-h-8 rounded-full px-2.5 text-xs font-medium', theme === v ? 'bg-surface shadow-sm' : 'text-muted')}
                >
                  {v}
                </button>
              ))}
            </div>
            <Toggle id="g-ro" label={t('dev.readOnly')} checked={readOnly} onChange={setReadOnly} />
            <Toggle id="g-dis" label={t('dev.disabled')} checked={disabled} onChange={setDisabled} />
            <Toggle id="g-busy" label={t('dev.busy')} checked={busy} onChange={setBusy} />
            <Toggle id="g-canvas" label={t('dev.canvas')} checked={canvas} onChange={setCanvas} />
          </div>
        </header>

        <main className={cn('mx-auto flex flex-col gap-8 px-3 py-4', canvas ? 'max-w-3xl' : 'max-w-2xl')}>
          <p className="text-sm text-muted">{t('dev.subtitle')}</p>
          <nav aria-label={t('dev.jump')}>
            <ul className="flex flex-wrap gap-1.5">
              {fixtures.map((f) => (
                <li key={f.name}>
                  <a href={`#/dev/widgets`} onClick={(e) => { e.preventDefault(); document.getElementById(`fx-${f.name}`)?.scrollIntoView() }} className="inline-block rounded-full bg-surface-2 px-2 py-1 font-mono text-xs hover:bg-surface-3">
                    {f.name}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          {fixtures.map((f) => (
            <section key={f.name} id={`fx-${f.name}`} aria-label={f.name} className="flex scroll-mt-28 flex-col gap-2">
              <h2 className="font-mono text-xs text-faint">{f.name}</h2>
              <WidgetLayoutContext.Provider value={canvas ? 'canvas' : 'inline'}>
              <WidgetView
                name={f.widget.payload.type ?? ''}
                widget={f.widget}
                complete
                readOnly={readOnly}
                disabled={disabled}
                busy={busy}
                emit={(event, { value, data, label }) =>
                  setEvents((e) => [{ ev: { widget_id: f.widget.id, event, value: value ?? null, data: data ?? {} }, label, at: new Date().toLocaleTimeString() }, ...e].slice(0, 30))
                }
              />
              </WidgetLayoutContext.Provider>
            </section>
          ))}
          <section aria-label="loading state" className="flex flex-col gap-2">
            <h2 className="font-mono text-xs text-faint">loading (args streaming)</h2>
            <WidgetView name="unit_compare" widget={null} complete={false} emit={() => undefined} />
            <h2 className="font-mono text-xs text-faint">error (bad args)</h2>
            <WidgetView name="unit_compare" widget={null} complete emit={() => undefined} onRetry={() => undefined} />
          </section>
        </main>

        <aside aria-label={t('dev.events')} className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 backdrop-blur">
          <div className="mx-auto max-w-2xl px-3 py-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{t('dev.events')}</h2>
              <Button size="sm" variant="ghost" onClick={() => setEvents([])}>
                {t('dev.clear')}
              </Button>
            </div>
            <ol className="max-h-32 overflow-y-auto font-mono text-[11px] leading-5" aria-live="polite">
              {events.length === 0 && <li className="text-muted">{t('dev.noEvents')}</li>}
              {events.map((e, i) => (
                <li key={i} className="truncate">
                  <span className="text-faint">{e.at}</span> “{e.label}” {JSON.stringify(e.ev)}
                </li>
              ))}
            </ol>
          </div>
        </aside>
      </div>
    </WidgetEnvContext.Provider>
  )
}

function Toggle({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Switch id={id} checked={checked} onCheckedChange={onChange} className="h-5 w-9 [&>span]:size-4 [&>span]:data-[state=checked]:translate-x-4" />
      <label htmlFor={id} className="text-xs">
        {label}
      </label>
    </span>
  )
}
