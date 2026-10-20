import { Database, ExternalLink, FileText } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/WidgetCard'
import { api, relative, type DocumentUpload } from '@/lib/api'
import { useApi } from '@/lib/useApi'

export function DocumentsTab() {
  const { t } = useTranslation()
  const [state, reload] = useApi(() => api.documents())
  if (state.status === 'loading') {
    return (
      <div className="flex flex-col gap-3" aria-busy>
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (state.status === 'error') return <ErrorState message={t('docs.loadError')} onRetry={reload} />
  const { uploads, sources } = state.data
  return (
    <div className="flex flex-col gap-6 lg:grid lg:grid-cols-2 lg:items-start">
      <section aria-labelledby="uploads-h" className="flex flex-col gap-3">
        <h2 id="uploads-h" className="text-lg font-semibold">
          {t('docs.uploads')}
        </h2>
        {uploads.length === 0 ? <EmptyState>{t('docs.noUploads')}</EmptyState> : uploads.map((u) => <UploadCard key={u.doc_id} u={u} />)}
      </section>
      <section aria-labelledby="sources-h" className="flex flex-col gap-3">
        <h2 id="sources-h" className="text-lg font-semibold">
          {t('docs.sources')}
        </h2>
        {sources.length === 0 ? (
          <EmptyState>{t('docs.noSources')}</EmptyState>
        ) : (
          <Card>
            <ul className="divide-y divide-border">
              {sources.map((s, i) => (
                <li key={s.id ?? `${s.label}-${i}`} className="flex gap-3 px-4 py-3">
                  <Database aria-hidden className="mt-0.5 size-4 shrink-0 text-faint" />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {s.label} {s.simulated && <Badge tone="warning">{t('common.simulated')}</Badge>}
                    </p>
                    {s.as_of && <p className="text-xs text-muted">{t('fig.asOfShort', { date: s.as_of })}</p>}
                    {s.note && <p className="text-sm text-muted">{s.note}</p>}
                    {s.url && (
                      <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-accent underline">
                        {t('fig.openSource')} <ExternalLink aria-hidden className="size-3" />
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </section>
    </div>
  )
}

function UploadCard({ u }: { u: DocumentUpload }) {
  const { t } = useTranslation()
  const [imgOk, setImgOk] = useState(true)
  const src = relative(u.image_url ?? '/' + api.docImageUrl(u.doc_id))
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start gap-3">
        <FileText aria-hidden className="mt-0.5 size-5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{u.filename ?? u.doc_id}</p>
          {u.uploaded_at && <p className="text-xs text-muted">{u.uploaded_at}</p>}
        </div>
        {u.status && <Badge>{u.status}</Badge>}
      </div>
      {imgOk && (
        <img src={src} alt={t('docs.redacted', { name: u.filename ?? u.doc_id })} loading="lazy" onError={() => setImgOk(false)} className="max-h-64 w-full rounded-lg border border-border object-contain bg-surface-2" />
      )}
      {u.lines && u.lines.length > 0 && (
        <div>
          <p className="text-sm font-medium">{t('docs.read')}</p>
          <ul className="mt-1 divide-y divide-border text-sm">
            {u.lines.map((l, i) => (
              <li key={`${l.label}-${i}`} className="flex items-center justify-between gap-2 py-1.5">
                <span>{l.label}</span>
                <span className="flex items-center gap-2">
                  {l.amount && <span className="tabular font-medium">{l.amount}</span>}
                  {l.status && (
                    <Badge tone={l.status === 'accepted' ? 'success' : l.status === 'rejected' ? 'danger' : l.status === 'check' ? 'warning' : 'neutral'}>
                      {isLineStatus(l.status) ? t(`w.upload_prompt.status.${l.status}`) : l.status}
                    </Badge>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {u.exclusions && u.exclusions.length > 0 && <p className="text-sm text-muted">{t('docs.excluded', { items: u.exclusions.join('; ') })}</p>}
    </Card>
  )
}

const LINE_STATUSES = ['pending', 'accepted', 'rejected', 'check'] as const
function isLineStatus(s: string): s is (typeof LINE_STATUSES)[number] {
  return (LINE_STATUSES as readonly string[]).includes(s)
}
