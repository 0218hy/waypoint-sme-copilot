import { Check, Pencil } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function ConfirmCard({ payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'confirm_card'>>) {
  const [sent, setSent] = useState<'confirm' | 'back' | null>(null)
  const off = disabled || readOnly || sent !== null
  return (
    <WidgetCard
      label={payload.title}
      title={payload.title}
      busy={busy}
      disabled={disabled}
      footer={
        !readOnly && (
          <>
            <Button
              disabled={off}
              onClick={() => {
                setSent('confirm')
                emit('confirm', { value: payload.step, data: { step: payload.step }, label: payload.confirm_label })
              }}
            >
              <Check aria-hidden />
              {payload.confirm_label}
            </Button>
            <Button
              variant="ghost"
              disabled={off}
              onClick={() => {
                setSent('back')
                emit('back', { value: payload.step, data: { step: payload.step }, label: payload.edit_label })
              }}
            >
              <Pencil aria-hidden />
              {payload.edit_label}
            </Button>
          </>
        )
      }
    >
      <dl className="flex flex-col divide-y divide-border">
        {payload.items.map((l) => (
          <div key={l.label} className="flex items-start justify-between gap-3 py-2 text-sm first:pt-0 last:pb-0">
            <dt className="text-muted">{l.label}</dt>
            <dd className="text-right font-medium">{l.value}</dd>
          </div>
        ))}
      </dl>
    </WidgetCard>
  )
}
