import { Check, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function ConsentCard({ payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'consent_card'>>) {
  const { t } = useTranslation()
  const [answered, setAnswered] = useState<boolean | null>(null)
  const off = disabled || readOnly || answered !== null
  return (
    <WidgetCard
      label={t('w.consent_card.title')}
      title={
        <span className="inline-flex items-center gap-2">
          <ShieldCheck aria-hidden className="size-5 text-accent" />
          {t('w.consent_card.title')}
        </span>
      }
      busy={busy}
      disabled={disabled}
      footer={
        !readOnly && (
          <>
            <Button
              disabled={off}
              onClick={() => {
                setAnswered(true)
                emit('consent', { value: true, data: { granted: true }, label: t('w.consent_card.agree') })
              }}
            >
              {t('w.consent_card.agree')}
            </Button>
            <Button
              variant="secondary"
              disabled={off}
              onClick={() => {
                setAnswered(false)
                emit('consent', { value: false, data: { granted: false }, label: t('w.consent_card.notNow') })
              }}
            >
              {t('w.consent_card.notNow')}
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        <section>
          <h4 className="font-medium">{t('w.consent_card.reads')}</h4>
          <ul className="mt-1 flex flex-col gap-1">
            {payload.reads.map((r) => (
              <li key={r} className="flex gap-2">
                <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-success" />
                {r}
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h4 className="font-medium">{t('w.consent_card.never')}</h4>
          <ul className="mt-1 flex flex-col gap-1">
            {payload.never.map((r) => (
              <li key={r} className="flex gap-2">
                <X aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
                {r}
              </li>
            ))}
          </ul>
        </section>
        <p className="rounded-xl bg-surface-2 px-3 py-2 text-muted">
          <span className="font-medium text-text">{t('w.consent_card.withdraw')} </span>
          {payload.withdraw}
        </p>
      </div>
    </WidgetCard>
  )
}
