import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/cn'

interface WidgetCardProps {
  title?: ReactNode
  subtitle?: ReactNode
  aside?: ReactNode
  children: ReactNode
  footer?: ReactNode
  busy?: boolean
  disabled?: boolean
  className?: string
  /** Accessible name for the region. */
  label?: string
}

/** The frame every widget shares: title, body, footer, and the busy / superseded states. */
export function WidgetCard({ title, subtitle, aside, children, footer, busy, disabled, className, label }: WidgetCardProps) {
  const { t } = useTranslation()
  return (
    <Card
      role="group"
      aria-label={label}
      aria-busy={busy || undefined}
      className={cn('@container relative w-full overflow-hidden', disabled && 'opacity-80', className)}
    >
      {(title || aside) && (
        <div className="flex items-start justify-between gap-3 px-4 pt-4">
          <div className="min-w-0">
            {title && <h3 className="text-base font-semibold leading-snug">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {aside && <div className="shrink-0">{aside}</div>}
        </div>
      )}
      <div className="px-4 py-3">{children}</div>
      {footer && <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">{footer}</div>}
      {busy && (
        <div className="absolute inset-0 flex items-center justify-center bg-surface/60 backdrop-blur-[1px]" role="status">
          <Loader2 aria-hidden className="size-6 animate-spin text-accent motion-reduce:animate-none" />
          <span className="sr-only">{t('widget.busy')}</span>
        </div>
      )}
    </Card>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="rounded-xl bg-surface-2 px-3 py-4 text-center text-sm text-muted">{children}</p>
}
