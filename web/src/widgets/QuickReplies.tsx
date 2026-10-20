import { Check } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

export default function QuickReplies({ payload, emit, disabled, readOnly }: WidgetProps<PayloadOf<'quick_replies'>>) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState<string | null>(null)
  const options = [...payload.options].sort(
    (a, b) => Number(b.value === payload.default) - Number(a.value === payload.default),
  )
  if (options.length === 0) return null
  const off = disabled || readOnly || picked !== null
  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label={t('w.quick_replies.label')} className="flex flex-wrap gap-2">
        {options.map((o) => {
          const isDefault = o.value === payload.default
          const isPicked = picked === o.value
          return (
            <button
              key={o.value}
              type="button"
              disabled={off}
              aria-pressed={isPicked}
              onClick={() => {
                setPicked(o.value)
                emit('reply', { value: o.value, data: { slot: payload.slot }, label: o.label })
              }}
              className={cn(
                'inline-flex min-h-11 max-w-full flex-col items-start justify-center rounded-2xl border px-4 py-2 text-left text-[15px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed',
                isPicked
                  ? 'border-accent bg-accent text-accent-fg'
                  : isDefault
                    ? 'border-accent bg-accent-soft text-accent hover:bg-accent-soft/70'
                    : 'border-border-strong bg-surface text-text hover:bg-surface-2',
                off && !isPicked && 'opacity-50',
              )}
            >
              <span className="inline-flex items-center gap-1.5">
                {isPicked && <Check aria-hidden className="size-4" />}
                {o.label}
              </span>
              {o.detail && <span className="text-xs font-normal opacity-80">{o.detail}</span>}
            </button>
          )
        })}
      </div>
      {payload.allow_text !== false && !off && <p className="text-xs text-faint">{t('w.quick_replies.orType')}</p>}
    </div>
  )
}
