import { Check, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AmountEditor } from '@/components/AmountEditor'
import { Button } from '@/components/ui/button'
import { EmptyState, WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

export default function MissingItems({ widget, payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'missing_items'>>) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState<string | null>(null)
  const [done, setDone] = useState<Record<string, string>>({})
  const off = disabled || readOnly
  return (
    <WidgetCard label={t('w.missing_items.title')} title={t('w.missing_items.title')} subtitle={t('w.missing_items.subtitle')} busy={busy} disabled={disabled}>
      {payload.items.length === 0 ? (
        <EmptyState>{t('w.missing_items.empty')}</EmptyState>
      ) : (
        <ul className="flex flex-col gap-2">
          {payload.items.map((it) => (
            <li key={it.value} className="rounded-xl border border-border p-3">
              <p className="font-medium">{it.label}</p>
              {it.detail && <p className="text-sm text-muted">{it.detail}</p>}
              {done[it.value] ? (
                <p className="mt-2 inline-flex items-center gap-1 text-sm text-success" role="status">
                  <Check aria-hidden className="size-4" />
                  {done[it.value]}
                </p>
              ) : editing === it.value ? (
                <div className="mt-2">
                  <AmountEditor
                    id={`mi-${widget.id}-${it.value}`}
                    label={t('w.missing_items.amountFor', { item: it.label })}
                    currency="S$"
                    onCancel={() => setEditing(null)}
                    onSave={(amount) => {
                      setEditing(null)
                      setDone((d) => ({ ...d, [it.value]: t('w.missing_items.added') }))
                      emit('edit_line', {
                        value: amount,
                        data: { id: it.value, value: amount, currency: 'SGD' },
                        label: t('w.missing_items.addedLabel', { item: it.label, amount: `S$${amount}` }),
                      })
                    }}
                  />
                </div>
              ) : (
                !readOnly && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" disabled={off} onClick={() => setEditing(it.value)}>
                      <Plus aria-hidden />
                      {t('w.missing_items.add')}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={off}
                      onClick={() => {
                        setDone((d) => ({ ...d, [it.value]: t('w.missing_items.included') }))
                        emit('mark_included', { value: it.value, data: { id: it.value }, label: t('w.missing_items.includedLabel', { item: it.label }) })
                      }}
                    >
                      <Check aria-hidden />
                      {t('w.missing_items.markIncluded')}
                    </Button>
                  </div>
                )
              )}
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}
