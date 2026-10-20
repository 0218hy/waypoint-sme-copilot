import { zodResolver } from '@hookform/resolvers/zod'
import { Check } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WidgetCard } from '@/components/WidgetCard'
import type { PayloadOf, WidgetProps } from './types'

type Field = 'profit_cny' | 'set_aside_cny'

export default function CheckinForm({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'checkin_form'>>) {
  const { t } = useTranslation()
  const [sent, setSent] = useState(false)
  const fields: Field[] = payload.fields ?? ['profit_cny', 'set_aside_cny']
  const money = (signed: boolean) =>
    z
      .string()
      .trim()
      .transform((s) => s.replace(/,/g, ''))
      .pipe(z.string().regex(signed ? /^-?\d{1,10}(\.\d{1,2})?$/ : /^\d{1,10}(\.\d{1,2})?$/, t(signed ? 'form.moneySigned' : 'form.money')))
  const schema = z.object({
    profit_cny: fields.includes('profit_cny') ? money(true) : z.string().optional(),
    set_aside_cny: fields.includes('set_aside_cny') ? money(false) : z.string().optional(),
  })
  const { register, handleSubmit, formState } = useForm<z.input<typeof schema>, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { profit_cny: '', set_aside_cny: '' },
  })
  const off = disabled || readOnly || sent
  const submit = handleSubmit((v) => {
    setSent(true)
    const value: Record<string, string> = {}
    for (const f of fields) if (v[f]) value[f] = v[f]!
    emit('checkin', {
      value,
      data: { goal_id: payload.goal_id, ...value, ...(payload.period ? { period: payload.period } : {}) },
      label: t('w.checkin_form.sentLabel', { period: payload.period_label }),
    })
  })
  return (
    <WidgetCard label={t('w.checkin_form.title')} title={t('w.checkin_form.title')} subtitle={payload.period_label} busy={busy} disabled={disabled}>
      {sent ? (
        <p role="status" className="inline-flex items-center gap-2 text-sm text-success">
          <Check aria-hidden className="size-4" />
          {t('w.checkin_form.thanks')}
        </p>
      ) : (
        <form onSubmit={submit} noValidate className="flex flex-col gap-3">
          {fields.map((f) => {
            const id = `ci-${widget.id}-${f}`
            const err = formState.errors[f]?.message
            return (
              <div key={f} className="flex flex-col gap-1">
                <label htmlFor={id} className="text-sm font-medium">
                  {t(`w.checkin_form.${f}`)}
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted">RMB</span>
                  <Input id={id} inputMode="decimal" autoComplete="off" disabled={off} aria-invalid={!!err} aria-describedby={err ? `${id}-err` : undefined} {...register(f)} />
                </div>
                {err && (
                  <p id={`${id}-err`} role="alert" className="text-sm text-danger">
                    {err}
                  </p>
                )}
              </div>
            )
          })}
          {!readOnly && (
            <Button type="submit" disabled={off} className="self-start">
              {t('w.checkin_form.submit')}
            </Button>
          )}
        </form>
      )}
    </WidgetCard>
  )
}
