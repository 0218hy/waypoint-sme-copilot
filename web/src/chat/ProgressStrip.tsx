import { Check, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { JourneyStep } from '@/lib/api'
import { cn } from '@/lib/cn'

interface Props {
  steps: JourneyStep[]
  disabled?: boolean
  onReopen: (step: JourneyStep) => void
}

/** The five journey steps; tapping a done (or stale) step reopens it on the server. */
export function ProgressStrip({ steps, disabled, onReopen }: Props) {
  const { t } = useTranslation()
  if (steps.length === 0) return null
  return (
    <nav aria-label={t('chat.progress')} className="border-b border-border bg-surface/90 px-2 py-2 backdrop-blur">
      <ol className="mx-auto flex max-w-2xl items-start justify-between gap-1">
        {steps.map((s, i) => {
          const tappable = (s.status === 'done' || s.status === 'stale') && !disabled
          const inner = (
            <>
              <span
                className={cn(
                  'flex size-7 items-center justify-center rounded-full text-xs font-semibold',
                  s.status === 'done' && 'bg-accent text-accent-fg',
                  s.status === 'current' && 'bg-surface text-accent ring-2 ring-accent',
                  s.status === 'todo' && 'bg-surface-3 text-muted',
                  s.status === 'stale' && 'bg-warning-soft text-warning ring-1 ring-warning',
                )}
              >
                {s.status === 'done' ? <Check aria-hidden className="size-4" /> : s.status === 'stale' ? <RotateCcw aria-hidden className="size-3.5" /> : i + 1}
              </span>
              <span
                className={cn(
                  'line-clamp-2 text-center text-[11px] leading-tight',
                  s.status === 'current' ? 'font-semibold text-text' : 'text-muted',
                )}
              >
                {s.label}
              </span>
              <span className="sr-only">{t(`chat.stepStatus.${s.status}`)}</span>
            </>
          )
          return (
            <li key={s.id} className="flex min-w-0 flex-1 flex-col items-center" aria-current={s.status === 'current' ? 'step' : undefined}>
              {tappable ? (
                <button
                  type="button"
                  onClick={() => onReopen(s)}
                  className="flex min-h-11 w-full flex-col items-center gap-1 rounded-lg px-0.5 py-0.5 hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-focus"
                  aria-label={t('chat.reopen', { step: s.label })}
                >
                  {inner}
                </button>
              ) : (
                <div className="flex w-full flex-col items-center gap-1 px-0.5 py-0.5">{inner}</div>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
