import { Camera, Check, CheckCheck, FileUp, Image as ImageIcon, Loader2, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'
import { useTranslation } from 'react-i18next'
import type { ExtractedRow } from '@/contracts/types'
import { ErrorState } from '@/components/ErrorState'
import { Fig } from '@/components/Fig'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WidgetCard } from '@/components/WidgetCard'
import { api, ApiError } from '@/lib/api'
import { cn } from '@/lib/cn'
import { useWidgetEnv } from './env'
import type { PayloadOf, WidgetProps } from './types'

type UploadState = { kind: 'idle' } | { kind: 'uploading'; name: string } | { kind: 'error'; message: string; file?: File } | { kind: 'done'; name: string }

export default function UploadPrompt(props: WidgetProps<PayloadOf<'upload_prompt'>>) {
  const { payload } = props
  const hasLines = (payload.extracted?.length ?? 0) > 0
  return hasLines ? <ExtractedView {...props} /> : <DropView {...props} />
}

function DropView({ payload, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'upload_prompt'>>) {
  const { t } = useTranslation()
  const env = useWidgetEnv()
  const [state, setState] = useState<UploadState>({ kind: 'idle' })
  const cameraRef = useRef<HTMLInputElement>(null)
  const accept = payload.accept ?? ['image/jpeg', 'image/png', 'image/heic', 'application/pdf']
  const maxMb = payload.max_mb ?? 10
  const off = disabled || readOnly || state.kind === 'uploading' || state.kind === 'done'

  const send = async (file: File) => {
    if (file.size > maxMb * 1024 * 1024) {
      setState({ kind: 'error', message: t('w.upload_prompt.tooBig', { mb: maxMb }) })
      return
    }
    setState({ kind: 'uploading', name: file.name })
    try {
      const { doc_id } = await env.upload(file)
      setState({ kind: 'done', name: file.name })
      emit('upload', { value: doc_id, data: { doc_id, filename: file.name }, label: t('w.upload_prompt.sentLabel', { name: file.name }) })
    } catch (e) {
      const status = e instanceof ApiError ? e.status : 0
      const message =
        status === 413 ? t('w.upload_prompt.tooBig', { mb: maxMb })
        : status === 429 ? t('w.upload_prompt.rateLimited')
        : e instanceof Error ? e.message : t('w.upload_prompt.failed')
      setState({ kind: 'error', message, file })
    }
  }

  const onDrop = (files: File[], rejected: FileRejection[]) => {
    if (rejected.length > 0) {
      const code = rejected[0]?.errors[0]?.code
      setState({
        kind: 'error',
        message: code === 'file-too-large' ? t('w.upload_prompt.tooBig', { mb: maxMb }) : t('w.upload_prompt.badType'),
      })
      return
    }
    if (files[0]) void send(files[0])
  }

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: Object.fromEntries(accept.map((m) => [m, []])),
    maxSize: maxMb * 1024 * 1024,
    multiple: false,
    disabled: off,
    noClick: true,
    noKeyboard: true,
  })

  return (
    <WidgetCard label={t('w.upload_prompt.title')} title={t('w.upload_prompt.title')} subtitle={t('w.upload_prompt.subtitle')} busy={busy} disabled={disabled}>
      <div className="flex flex-col gap-3">
        <div
          {...getRootProps()}
          className={cn(
            'flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-4 py-6 text-center transition-colors',
            isDragActive ? 'border-accent bg-accent-soft' : 'border-border-strong bg-surface-2/50',
            off && 'opacity-60',
          )}
        >
          <input {...getInputProps()} aria-label={t('w.upload_prompt.choose')} />
          {state.kind === 'uploading' ? (
            <p className="inline-flex items-center gap-2 text-sm" role="status">
              <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
              {t('w.upload_prompt.uploading', { name: state.name })}
            </p>
          ) : state.kind === 'done' ? (
            <p className="inline-flex items-center gap-2 text-sm text-success" role="status">
              <Check aria-hidden className="size-4" />
              {t('w.upload_prompt.done', { name: state.name })}
            </p>
          ) : (
            <>
              <FileUp aria-hidden className="size-8 text-faint" />
              <p className="hidden text-sm text-muted sm:block">{t('w.upload_prompt.drop')}</p>
              <div className="flex flex-wrap justify-center gap-2">
                <Button disabled={off} onClick={() => cameraRef.current?.click()}>
                  <Camera aria-hidden />
                  {t('w.upload_prompt.camera')}
                </Button>
                <Button variant="secondary" disabled={off} onClick={open}>
                  <FileUp aria-hidden />
                  {t('w.upload_prompt.choose')}
                </Button>
              </div>
              <p className="text-xs text-faint">{t('w.upload_prompt.limits', { mb: maxMb })}</p>
              {env.sampleQuote && (
                <Button
                  variant="link"
                  size="sm"
                  disabled={off}
                  onClick={async () => {
                    try {
                      const file = await env.sampleQuote!()
                      await send(file)
                    } catch {
                      setState({ kind: 'error', message: t('demo.sampleFailed') })
                    }
                  }}
                >
                  <ImageIcon aria-hidden />
                  {t('demo.sample')}
                </Button>
              )}
            </>
          )}
          <input
            ref={cameraRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (f) void send(f)
            }}
          />
        </div>
        {state.kind === 'error' && (
          <ErrorState
            message={state.message}
            onRetry={state.file ? () => void send(state.file!) : () => setState({ kind: 'idle' })}
          />
        )}
        <p className="text-xs text-muted">{t('w.upload_prompt.privacy')}</p>
      </div>
    </WidgetCard>
  )
}

const STATUS_TONE = { pending: 'neutral', accepted: 'success', rejected: 'danger', check: 'warning' } as const

function ExtractedView({ payload, widget, emit, disabled, readOnly, busy }: WidgetProps<PayloadOf<'upload_prompt'>>) {
  const { t } = useTranslation()
  const env = useWidgetEnv()
  const [focus, setFocus] = useState<string | null>(null)
  const [decided, setDecided] = useState<Record<string, ExtractedRow['status'] | undefined>>({})
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null)
  const [imgError, setImgError] = useState(false)
  // optimistic: which cost line the owner assigned an unmatched row to, and what each covered line is
  const [assigned, setAssigned] = useState<Record<string, string>>({})
  const [whole, setWhole] = useState<Record<string, boolean>>({})
  const off = disabled || readOnly
  const imageUrl = payload.image_url ?? (payload.doc_id ? '/' + api.docImageUrl(payload.doc_id) : null)
  const lines = payload.extracted ?? []
  // Lines accept-all takes: the pending ones. "Please check" lines (read with low confidence) need a tap each.
  const undecided = lines.filter((r) => (decided[r.id] ?? r.status) === 'pending')
  const toCheck = lines.filter((r) => (decided[r.id] ?? r.status) === 'check')

  const box = (row: ExtractedRow) => {
    if (!row.bbox) return null
    let [x0, y0, x1, y1] = row.bbox
    // Normalised (0–1) by default; pixel boxes are scaled by the image's natural size.
    if (Math.max(x0, y0, x1, y1) > 1) {
      if (!natural) return null
      x0 /= natural.w
      x1 /= natural.w
      y0 /= natural.h
      y1 /= natural.h
    }
    return { left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }
  }

  const decide = (row: ExtractedRow, ev: 'accept_line' | 'reject_line') => {
    setDecided((d) => ({ ...d, [row.id]: ev === 'accept_line' ? 'accepted' : 'rejected' }))
    emit(ev, {
      value: row.id,
      data: { id: row.id },
      label: t(ev === 'accept_line' ? 'w.upload_prompt.acceptedLabel' : 'w.upload_prompt.rejectedLabel', { line: row.label }),
    })
  }

  const assign = (row: ExtractedRow, key: string) => {
    setAssigned((a) => ({ ...a, [row.id]: key }))
    const line = payload.assignable?.find((o) => o.value === key)?.label
    emit('assign_line', {
      value: row.id,
      data: { id: row.id, key: key || null },
      label: line ? t('w.upload_prompt.assignedLabel', { row: row.label, line }) : t('w.upload_prompt.unassignedLabel', { row: row.label }),
    })
  }

  const cover = (key: string, label: string, all: boolean) => {
    setWhole((w) => ({ ...w, [key]: all }))
    emit('set_coverage', {
      value: key,
      data: { doc_id: payload.doc_id ?? null, key, whole: all },
      label: t(all ? 'w.upload_prompt.coversAllLabel' : 'w.upload_prompt.coversPartLabel', { line: label }),
    })
  }

  const coverage = payload.coverage ?? []

  return (
    <WidgetCard
      label={t('w.upload_prompt.readTitle')}
      title={t('w.upload_prompt.readTitle')}
      subtitle={t('w.upload_prompt.readSubtitle')}
      aside={payload.reader_mode === 'replay' ? <Badge tone="warning">{t('w.upload_prompt.replay')}</Badge> : undefined}
      busy={busy}
      disabled={disabled}
    >
      <div className="flex flex-col gap-4">
        {imageUrl && !imgError && (
          <div className="relative overflow-hidden rounded-xl border border-border bg-surface-2">
            <img
              src={env.resolveUrl(imageUrl)}
              alt={t('w.upload_prompt.imageAlt')}
              className="block h-auto w-full"
              onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              onError={() => setImgError(true)}
            />
            {lines.map((row) => {
              const style = box(row)
              if (!style) return null
              const status = decided[row.id] ?? row.status
              return (
                <span
                  key={row.id}
                  aria-hidden
                  style={style}
                  className={cn(
                    'pointer-events-none absolute rounded-sm border-2 transition-colors',
                    focus === row.id ? 'border-accent bg-accent/20' : status === 'check' ? 'border-warning bg-warning/10' : status === 'rejected' ? 'border-danger/60' : 'border-accent/60',
                  )}
                />
              )
            })}
          </div>
        )}
        {imgError && <p className="text-sm text-muted">{t('w.upload_prompt.noImage')}</p>}

        {!readOnly && undecided.length > 0 && (
          <Button
            disabled={off}
            className="self-start"
            onClick={() => {
              setDecided((d) => ({ ...d, ...Object.fromEntries(undecided.map((r) => [r.id, 'accepted' as const])) }))
              emit('accept_all', {
                value: payload.doc_id ?? null,
                data: { doc_id: payload.doc_id ?? null },
                label: t('w.upload_prompt.acceptAllLabel', { count: undecided.length }),
              })
            }}
          >
            <CheckCheck aria-hidden />
            {t('w.upload_prompt.acceptAll')}
          </Button>
        )}
        {!readOnly && toCheck.length > 0 && (
          <p className="text-sm text-warning">{t('w.upload_prompt.checkEach', { count: toCheck.length })}</p>
        )}
        <ul className="flex flex-col gap-2">
          {lines.map((row) => {
            const status = decided[row.id] ?? row.status
            return (
              <li
                key={row.id}
                onMouseEnter={() => setFocus(row.id)}
                onMouseLeave={() => setFocus(null)}
                onFocus={() => setFocus(row.id)}
                className={cn('rounded-xl border p-3', focus === row.id ? 'border-accent' : status === 'check' ? 'border-warning bg-warning-soft/40' : 'border-border')}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium">{row.label}</p>
                    {row.matched_label ? (
                      <p className="text-xs text-muted">
                        {t(row.part && !whole[row.matched_key ?? ''] ? 'w.upload_prompt.partOf' : 'w.upload_prompt.replaces', { line: row.matched_label })}
                      </p>
                    ) : readOnly ? (
                      <p className="text-xs text-muted">{t('w.upload_prompt.unmatched')}</p>
                    ) : (
                      <div className="mt-1 flex flex-col gap-1">
                        <label htmlFor={`assign-${widget.id}-${row.id}`} className="text-xs text-muted">
                          {t('w.upload_prompt.whichCost')}
                        </label>
                        <select
                          id={`assign-${widget.id}-${row.id}`}
                          disabled={off}
                          value={assigned[row.id] ?? ''}
                          onChange={(e) => assign(row, e.target.value)}
                          className="min-h-11 rounded-xl border border-border-strong bg-surface px-3 text-[15px] focus-visible:outline-2 focus-visible:outline-focus"
                        >
                          <option value="">{t('w.upload_prompt.notOnCard')}</option>
                          {(payload.assignable ?? []).map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    {row.amount ? <Fig widget={widget} id={row.amount} className="font-semibold" /> : <span className="text-sm text-faint">{t('w.upload_prompt.noAmount')}</span>}
                    <Badge tone={STATUS_TONE[status]}>{t(`w.upload_prompt.status.${status}`)}</Badge>
                  </div>
                </div>
                {status === 'check' && (
                  <p className="mt-1 text-xs text-warning">{t('w.upload_prompt.pleaseCheck')}</p>
                )}
                {!readOnly && (status === 'pending' || status === 'check') && (
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" disabled={off} onClick={() => decide(row, 'accept_line')} aria-label={t('w.upload_prompt.acceptAria', { line: row.label })}>
                      <Check aria-hidden />
                      {t('w.upload_prompt.accept')}
                    </Button>
                    <Button size="sm" variant="secondary" disabled={off} onClick={() => decide(row, 'reject_line')} aria-label={t('w.upload_prompt.rejectAria', { line: row.label })}>
                      <X aria-hidden />
                      {t('w.upload_prompt.reject')}
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
        {coverage.length > 0 && (
          <section className="flex flex-col gap-2 rounded-xl border border-border p-3 text-sm">
            {coverage.map((c) => {
              const all = whole[c.key] ?? c.whole
              return (
                <div key={c.key} className="flex flex-col gap-2" role="group" aria-label={t('w.upload_prompt.coversQuestion', { line: c.label })}>
                  <p className="font-medium">{t('w.upload_prompt.coversQuestion', { line: c.label })}</p>
                  <p className="text-xs text-muted">{t(all ? 'w.upload_prompt.coversAllNote' : 'w.upload_prompt.coversPartNote')}</p>
                  {!readOnly && (
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant={all ? 'primary' : 'secondary'} aria-pressed={all} disabled={off} onClick={() => !all && cover(c.key, c.label, true)}>
                        {t('w.upload_prompt.coversAll')}
                      </Button>
                      <Button size="sm" variant={!all ? 'primary' : 'secondary'} aria-pressed={!all} disabled={off} onClick={() => all && cover(c.key, c.label, false)}>
                        {t('w.upload_prompt.coversPart')}
                      </Button>
                    </div>
                  )}
                </div>
              )
            })}
          </section>
        )}
        {(payload.exclusions?.length ?? 0) > 0 && (
          <section className="rounded-xl bg-warning-soft/60 p-3 text-sm">
            <h4 className="font-medium">{t('w.upload_prompt.exclusions')}</h4>
            <ul className="mt-1 list-disc pl-5 text-muted">
              {payload.exclusions!.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </section>
        )}
        <p className="text-xs text-muted">{t('w.upload_prompt.untrustedNote')}</p>
      </div>
    </WidgetCard>
  )
}
