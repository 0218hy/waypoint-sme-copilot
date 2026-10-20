import { PanelRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { WidgetLayoutContext } from '@/widgets/layout'
import type { Emit, WidgetType } from '@/widgets/types'
import { WidgetView } from '@/widgets/WidgetView'
import { heroTitleKey } from './heroTitle'
import type { ToolEntry } from './transcript'

interface Props {
  entry: ToolEntry | undefined
  isLatest: boolean
  disabled: boolean
  busy: boolean
  emit: Emit
  onRetry: () => void
  onShowLatest: () => void
}

/** Desktop (≥1280px): the most recent hero widget, drawn large beside the chat. */
export function Canvas({ entry, isLatest, disabled, busy, emit, onRetry, onShowLatest }: Props) {
  const { t } = useTranslation()
  return (
    <aside aria-label={t('canvas.label')} className="flex min-h-0 flex-col border-l border-border bg-bg">
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-3">
        <h2 className="inline-flex items-center gap-2 text-sm font-semibold">
          <PanelRight aria-hidden className="size-4 text-accent" />
          {entry ? t(heroTitleKey(entry.name as Extract<WidgetType, 'area_map'>)) : t('canvas.label')}
        </h2>
        {entry && !isLatest && (
          <button type="button" onClick={onShowLatest} className="min-h-9 rounded-lg px-2 text-sm font-medium text-accent hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-focus">
            {t('canvas.backToLatest')}
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
        {entry ? (
          <WidgetLayoutContext.Provider value="canvas">
            {!isLatest && <p className="mb-3 rounded-xl bg-info-soft px-3 py-2 text-sm">{t('canvas.olderNote')}</p>}
            <WidgetView key={entry.key} name={entry.name} widget={entry.widget} complete emit={emit} disabled={disabled} busy={busy} onRetry={onRetry} />
          </WidgetLayoutContext.Provider>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-muted">
            <PanelRight aria-hidden className="size-8 text-faint" />
            <p className="max-w-xs text-sm">{t('canvas.empty')}</p>
          </div>
        )}
      </div>
    </aside>
  )
}
