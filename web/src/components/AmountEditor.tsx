import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/** Inline amount form (react-hook-form + zod). Sends the typed amount as a decimal string. */
export function AmountEditor({
  id,
  label,
  currency,
  onSave,
  onCancel,
  saveLabel,
}: {
  id: string
  label: string
  currency: 'S$' | 'RMB'
  onSave: (amount: string) => void
  onCancel: () => void
  saveLabel?: string
}) {
  const { t } = useTranslation()
  const schema = z.object({
    amount: z
      .string()
      .trim()
      .transform((s) => s.replace(/,/g, ''))
      .pipe(z.string().regex(/^\d{1,10}(\.\d{1,2})?$/, t('form.money'))),
  })
  const { register, handleSubmit, formState } = useForm<z.input<typeof schema>, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { amount: '' },
  })
  const err = formState.errors.amount?.message
  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.stopPropagation()
        void handleSubmit(({ amount }) => onSave(amount))(e)
      }}
      className="flex flex-col gap-2 rounded-xl bg-surface-2 p-3"
    >
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted">{currency}</span>
        <Input
          id={id}
          autoFocus
          inputMode="decimal"
          autoComplete="off"
          aria-invalid={!!err}
          aria-describedby={err ? `${id}-err` : undefined}
          {...register('amount')}
        />
      </div>
      {err && (
        <p id={`${id}-err`} role="alert" className="text-sm text-danger">
          {err}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm">
          {saveLabel ?? t('common.save')}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  )
}
