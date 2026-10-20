import { AlertTriangle, RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-xl bg-danger-soft px-3 py-3 text-sm text-danger">
      <p className="inline-flex items-center gap-2 font-medium">
        <AlertTriangle aria-hidden className="size-4" />
        {message ?? t('common.loadError')}
      </p>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          <RotateCw aria-hidden />
          {t('common.retry')}
        </Button>
      )}
    </div>
  )
}
