import { AlertTriangle } from 'lucide-react'
import { Component, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/contracts/types'
import { ErrorState } from '@/components/ErrorState'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { rendererFor } from './registry'
import type { Emit } from './types'

export interface WidgetViewProps {
  /** Tool call name (the widget type). */
  name: string
  /** The parsed Widget, or null while its args are still streaming / failed to parse. */
  widget: Widget | null
  /** True once TOOL_CALL_END has arrived (or the call came from a snapshot). */
  complete: boolean
  emit: Emit
  disabled?: boolean
  readOnly?: boolean
  busy?: boolean
  onRetry?: () => void
}

/** Renders one widget from its registry entry, with loading and error states. */
export function WidgetView({ name, widget, complete, emit, disabled = false, readOnly = false, busy = false, onRetry }: WidgetViewProps) {
  const { t } = useTranslation()
  const renderer = rendererFor(name)
  if (!widget) {
    if (!complete) return <WidgetSkeleton />
    return (
      <Card className="p-4">
        <ErrorState message={t('widget.parseError')} onRetry={onRetry} />
      </Card>
    )
  }
  if (!renderer || widget.payload?.type !== name) {
    return (
      <Card className="flex items-center gap-2 p-4 text-sm text-muted">
        <AlertTriangle aria-hidden className="size-4" />
        {t('widget.unsupported')}
      </Card>
    )
  }
  const Render = renderer.render
  return (
    <WidgetErrorBoundary fallback={<Card className="p-4"><ErrorState message={t('widget.crashed')} onRetry={onRetry} /></Card>}>
      <Render widget={widget} payload={widget.payload} emit={emit} disabled={disabled} readOnly={readOnly} busy={busy} />
    </WidgetErrorBoundary>
  )
}

export function WidgetSkeleton() {
  const { t } = useTranslation()
  return (
    <Card className="flex flex-col gap-3 p-4" role="status" aria-label={t('widget.loading')}>
      <Skeleton className="h-5 w-1/2" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </Card>
  )
}

class WidgetErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { error: Error | null }> {
  override state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  override componentDidCatch(error: Error) {
    console.error('[waypoint] widget crashed', error)
  }
  override render() {
    return this.state.error ? this.props.fallback : this.props.children
  }
}
