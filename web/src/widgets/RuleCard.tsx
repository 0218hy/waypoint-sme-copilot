import { Scale } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SourceLine } from '@/components/Fig'
import { cn } from '@/lib/cn'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function RuleCard({ payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'rule_card'>>) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState<string | null>(null)
  const off = disabled || readOnly || picked !== null
  return (
    <WidgetCard
      label={payload.title}
      title={
        <span className="inline-flex items-start gap-2">
          <Scale aria-hidden className="mt-0.5 size-5 shrink-0 text-danger" />
          {payload.title}
        </span>
      }
      className="border-danger/40"
      busy={busy}
      disabled={disabled}
    >
      <p className="text-[15px]">{payload.message}</p>
      <div className="mt-3 rounded-xl bg-danger-soft/60 px-3 py-2 text-sm">
        <p className="font-medium">{t('w.rule_card.consequence')}</p>
        <p>{payload.consequence}</p>
      </div>
      <SourceLine source={payload.source} className="mt-2" />
      <p className="mt-1 text-xs text-faint">{t('w.rule_card.rule', { rule: payload.rule_id })}</p>
      {payload.options.length > 0 && (
        <section className="mt-3">
          <h4 className="text-sm font-medium">{t('w.rule_card.instead')}</h4>
          <ul className="mt-2 flex flex-col gap-2">
            {payload.options.map((o) => (
              <li key={o.value}>
                <button
                  type="button"
                  disabled={off}
                  aria-pressed={picked === o.value}
                  onClick={() => {
                    setPicked(o.value)
                    emit('select_option', { value: o.value, data: { id: o.value, rule_id: payload.rule_id }, label: o.label })
                  }}
                  className={cn(
                    'flex min-h-12 w-full flex-col items-start rounded-xl border px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-not-allowed',
                    picked === o.value ? 'border-accent bg-accent-soft' : 'border-border-strong hover:bg-surface-2',
                    off && picked !== o.value && 'opacity-60',
                  )}
                >
                  <span className="font-medium">{o.label}</span>
                  {o.detail && <span className="text-sm text-muted">{o.detail}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </WidgetCard>
  )
}
