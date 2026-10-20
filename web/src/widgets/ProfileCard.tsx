import { zodResolver } from '@hookform/resolvers/zod'
import { Pencil } from 'lucide-react'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import type { ProfileField } from '@/contracts/types'
import { Fig } from '@/components/Fig'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WidgetCard } from '@/components/WidgetCard'
import { cn } from '@/lib/cn'
import type { PayloadOf, WidgetProps } from './types'

const SOURCE_TONE = { feed: 'accent', owner: 'info', computed: 'neutral', missing: 'warning' } as const

export default function ProfileCard(props: WidgetProps<PayloadOf<'profile_card'>>) {
  const { payload, widget, emit, disabled, readOnly, busy } = props
  const { t } = useTranslation()
  const [editing, setEditing] = useState<string | null>(null)
  const off = disabled || readOnly
  return (
    <WidgetCard
      label={t('w.profile_card.title')}
      title={t('w.profile_card.title')}
      aside={payload.simulated_feed ? <Badge tone="warning">{t('w.profile_card.simulatedFeed')}</Badge> : undefined}
      busy={busy}
      disabled={disabled}
      footer={
        !readOnly && (
          <Button
            disabled={off || editing !== null}
            onClick={() => emit('confirm', { label: t('w.profile_card.confirm') })}
            className="w-full @sm:w-auto"
          >
            {t('w.profile_card.confirm')}
          </Button>
        )
      }
    >
      {payload.fields.length === 0 ? (
        <p className="text-sm text-muted">{t('w.profile_card.empty')}</p>
      ) : (
        <ul className="-my-1 divide-y divide-border">
          {payload.fields.map((f) => (
            <li key={f.key} className="py-2.5">
              {editing === f.key ? (
                <FieldEditor
                  field={f}
                  onCancel={() => setEditing(null)}
                  onSave={(value, text) => {
                    setEditing(null)
                    emit('edit', { value, data: { field: f.key, value }, label: `${f.label}: ${text}` })
                  }}
                />
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-muted">{f.label}</p>
                    <p className={cn('font-medium', f.source === 'missing' && 'text-warning')}>
                      {f.figure ? <Fig widget={widget} id={f.figure} /> : (f.text ?? t('w.profile_card.notSet'))}
                    </p>
                    <Badge tone={SOURCE_TONE[f.source]} className="mt-1">
                      {t(`w.profile_card.source.${f.source}`)}
                    </Badge>
                  </div>
                  {f.editable !== false && !off && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditing(f.key)}
                      aria-label={t('w.profile_card.editField', { field: f.label })}
                    >
                      <Pencil aria-hidden />
                      {t('common.edit')}
                    </Button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </WidgetCard>
  )
}

function FieldEditor({
  field,
  onSave,
  onCancel,
}: {
  field: ProfileField
  onSave: (value: string | string[], text: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const kind = field.input ?? 'text'
  const schema = z.object({
    value:
      kind === 'money_cny'
        ? z.string().trim().regex(/^\d{1,12}(\.\d{1,2})?$/, t('form.money'))
        : kind === 'count'
          ? z.string().trim().regex(/^\d{1,6}$/, t('form.count'))
          : kind === 'multi'
            ? z.array(z.string()).min(1, t('form.pickOne'))
            : z.string().trim().min(1, t('form.required')).max(200),
  })
  type Values = z.infer<typeof schema>
  const { register, handleSubmit, formState, control, setValue } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { value: kind === 'multi' ? [] : '' },
  })
  const id = `pf-${field.key}`
  const current = useWatch({ control, name: 'value' })
  const error = formState.errors.value?.message
  const submit = handleSubmit(({ value }) => {
    if (Array.isArray(value)) {
      const labels = (field.options ?? []).filter((o) => value.includes(o.value)).map((o) => o.label)
      onSave(value, labels.join(', '))
    } else if (kind === 'enum') {
      onSave(value, (field.options ?? []).find((o) => o.value === value)?.label ?? value)
    } else if (kind === 'money_cny') {
      onSave(value, `RMB ${value}`)
    } else {
      onSave(value, value)
    }
  })
  return (
    <form onSubmit={submit} className="flex flex-col gap-2" noValidate>
      <label htmlFor={id} className="text-sm font-medium">
        {field.label}
      </label>
      {kind === 'enum' || kind === 'multi' ? (
        <div id={id} role="group" aria-label={field.label} className="flex flex-wrap gap-2">
          {(field.options ?? []).map((o) => {
            const on = Array.isArray(current) ? current.includes(o.value) : current === o.value
            return (
              <button
                key={o.value}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  if (kind === 'multi') {
                    const arr = Array.isArray(current) ? current : []
                    setValue('value', on ? arr.filter((v) => v !== o.value) : [...arr, o.value], { shouldValidate: true })
                  } else {
                    setValue('value', o.value, { shouldValidate: true })
                  }
                }}
                className={cn(
                  'min-h-11 rounded-xl border px-3 text-sm focus-visible:outline-2 focus-visible:outline-focus',
                  on ? 'border-accent bg-accent-soft text-accent' : 'border-border-strong bg-surface',
                )}
              >
                {o.label}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          {kind === 'money_cny' && <span className="text-sm text-muted">RMB</span>}
          <Input
            id={id}
            autoFocus
            inputMode={kind === 'money_cny' ? 'decimal' : kind === 'count' ? 'numeric' : 'text'}
            aria-invalid={!!error}
            aria-describedby={error ? `${id}-err` : undefined}
            {...register('value')}
          />
        </div>
      )}
      {error && (
        <p id={`${id}-err`} role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm">
          {t('common.save')}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  )
}
