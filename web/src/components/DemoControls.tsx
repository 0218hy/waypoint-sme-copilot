import { BadgeCheck, FastForward, Landmark, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useOptionalChat } from '@/chat/chatContext'
import { api, type DemoScenario, type WebankInstruction } from '@/lib/api'
import { cn } from '@/lib/cn'

const SCENARIOS: DemoScenario[] = ['none', 'sales_dip', 'channel_shift', 'above_normal_draw']

/** Demo only: move the simulated clock forward and run the weekly Goal Keeper check. */
export function DemoControls({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const [scenario, setScenario] = useState<DemoScenario>('none')
  const [busy, setBusy] = useState<number | null>(null)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const id = compact ? 'demo-scenario-rail' : 'demo-scenario'

  const advance = async (weeks: number) => {
    setBusy(weeks)
    setResult(null)
    try {
      await api.demoAdvance(weeks, scenario)
      setResult({ ok: true, text: t('demo.done', { weeks }) })
      window.dispatchEvent(new CustomEvent('waypoint:demo-advanced'))
    } catch {
      setResult({ ok: false, text: t('demo.failed') })
    } finally {
      setBusy(null)
    }
  }

  return (
    <section aria-labelledby={`${id}-h`} className={cn('flex flex-col gap-2', compact ? 'rounded-2xl border border-dashed border-warning/50 bg-warning-soft/30 p-3' : '')}>
      <div className="flex items-center justify-between gap-2">
        <h2 id={`${id}-h`} className={compact ? 'text-xs font-semibold uppercase tracking-wide text-faint' : 'font-semibold'}>
          {t('demo.title')}
        </h2>
        <Badge tone="warning">{t('demo.simulated')}</Badge>
      </div>
      <p className="text-xs text-muted">{t('demo.hint')}</p>
      <label htmlFor={id} className="text-xs font-medium">
        {t('demo.scenario')}
      </label>
      <select
        id={id}
        value={scenario}
        onChange={(e) => setScenario(e.target.value as DemoScenario)}
        className="min-h-10 rounded-xl border border-border-strong bg-surface px-2 text-sm focus-visible:outline-2 focus-visible:outline-focus"
      >
        {SCENARIOS.map((s) => (
          <option key={s} value={s}>
            {t(`demo.scenarios.${s}`)}
          </option>
        ))}
      </select>
      <div className="flex flex-wrap gap-2">
        {[4, 8].map((w) => (
          <Button key={w} size="sm" variant="secondary" disabled={busy !== null} onClick={() => void advance(w)}>
            {busy === w ? <Loader2 aria-hidden className="animate-spin" /> : <FastForward aria-hidden />}
            {t('demo.skip', { weeks: w })}
          </Button>
        ))}
      </div>
      {result && (
        <p role="status" className={cn('text-xs', result.ok ? 'text-success' : 'text-danger')}>
          {result.text}
        </p>
      )}
      <WebankSigning />
    </section>
  )
}

/**
 * Demo only: WeBank's own signing flow, simulated. Waypoint prepares the monthly transfer (the owner
 * approves its card in the chat); the owner signs it in WeBank, never in Waypoint.
 */
function WebankSigning() {
  const { t } = useTranslation()
  const running = useOptionalChat()?.running ?? false
  const [items, setItems] = useState<WebankInstruction[]>([])
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const load = useCallback(() => {
    api.demoWebank().then(
      (r) => setItems(Array.isArray(r?.instructions) ? r.instructions : []),
      () => setItems([]),
    )
  }, [])
  useEffect(() => {
    if (!running) load() // after each chat turn: a card approved there may have prepared one
  }, [running, load])
  if (items.length === 0) return null
  const sign = async (id: string) => {
    setBusy(true)
    setFailed(false)
    try {
      const r = await api.demoWebankSign(id)
      setItems(Array.isArray(r?.instructions) ? r.instructions : [])
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mt-1 flex flex-col gap-2 rounded-xl border border-border bg-surface p-3">
      <p className="inline-flex items-center gap-1.5 text-xs font-semibold">
        <Landmark aria-hidden className="size-4 text-accent" />
        {t('demo.webank.title')}
      </p>
      {items.map((it) =>
        it.status === 'signed' ? (
          <p key={it.id} role="status" className="inline-flex gap-1.5 text-xs text-success">
            <BadgeCheck aria-hidden className="mt-0.5 size-4 shrink-0" />
            {t('demo.webank.signed', { amount: it.amount, start: it.start })}
          </p>
        ) : (
          <div key={it.id} className="flex flex-col gap-2">
            <p className="text-xs text-muted">{t('demo.webank.pending', { amount: it.amount, into: it.into, start: it.start })}</p>
            <Button size="sm" disabled={busy} onClick={() => void sign(it.id)} className="self-start">
              {busy ? <Loader2 aria-hidden className="animate-spin" /> : <Landmark aria-hidden />}
              {t('demo.webank.sign')}
            </Button>
          </div>
        ),
      )}
      {failed && (
        <p role="alert" className="text-xs text-danger">
          {t('demo.webank.failed')}
        </p>
      )}
    </div>
  )
}
