import { Check, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { JourneyStep } from '@/lib/api'
import { cn } from '@/lib/cn'

/** Desktop: the five steps as a vertical rail. Done (or stale) steps reopen on tap, like the strip. */
export function StepRail({ steps, disabled, onReopen }: { steps: JourneyStep[]; disabled?: boolean; onReopen: (s: JourneyStep) => void }) {
  const { t } = useTranslation()
  if (steps.length === 0) return null
  return (
    <nav aria-label={t('chat.progress')}>
      <h2 className="px-2 text-xs font-semibold uppercase tracking-wide text-faint">{t('chat.progress')}</h2>
      <ol className="mt-2 flex flex-col">
        {steps.map((s, i) => {
          const tappable = (s.status === 'done' || s.status === 'stale') && !disabled
          const last = i === steps.length - 1
          const dot = (
            <span
              className={cn(
                'relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                s.status === 'done' && 'bg-accent text-accent-fg',
                s.status === 'current' && 'bg-surface text-accent ring-2 ring-accent',
                s.status === 'todo' && 'bg-surface-3 text-muted',
                s.status === 'stale' && 'bg-warning-soft text-warning ring-1 ring-warning',
              )}
            >
              {s.status === 'done' ? <Check aria-hidden className="size-4" /> : s.status === 'stale' ? <RotateCcw aria-hidden className="size-3.5" /> : i + 1}
            </span>
          )
          const body = (
            <>
              {dot}
              <span className="min-w-0 flex-1">
                <span className={cn('block text-sm leading-tight', s.status === 'current' ? 'font-semibold text-text' : 'text-muted')}>{s.label}</span>
                {s.status === 'stale' && <span className="block text-xs text-warning">{t('chat.stepStatus.stale')}</span>}
                {tappable && <span className="block text-xs text-faint">{t('chat.tapToReopen')}</span>}
              </span>
              <span className="sr-only">{t(`chat.stepStatus.${s.status}`)}</span>
            </>
          )
          return (
            <li key={s.id} className="relative" aria-current={s.status === 'current' ? 'step' : undefined}>
              {!last && <span aria-hidden className={cn('absolute top-9 bottom-0 left-[21px] w-0.5', s.status === 'done' ? 'bg-accent/50' : 'bg-border')} />}
              {tappable ? (
                <button
                  type="button"
                  onClick={() => onReopen(s)}
                  aria-label={t('chat.reopen', { step: s.label })}
                  className="flex min-h-12 w-full items-start gap-3 rounded-xl px-2 py-1.5 text-left hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-focus"
                >
                  {body}
                </button>
              ) : (
                <div className="flex min-h-12 items-start gap-3 px-2 py-1.5">{body}</div>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
