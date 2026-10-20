import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/cn'
import type { Lang } from '@/lib/api'

export function LanguageToggle({ onChange }: { onChange?: (lang: Lang) => void }) {
  const { t, i18n } = useTranslation()
  const current = i18n.language === 'zh' ? 'zh' : 'en'
  const opts: [Lang, string][] = [
    ['en', 'EN'],
    ['zh', '中文'],
  ]
  return (
    <div role="group" aria-label={t('shell.language')} className="inline-flex rounded-full bg-surface-2 p-0.5">
      {opts.map(([lang, label]) => (
        <button
          key={lang}
          type="button"
          lang={lang}
          aria-pressed={current === lang}
          onClick={() => {
            if (current === lang) return
            void i18n.changeLanguage(lang)
            onChange?.(lang)
          }}
          className={cn(
            'min-h-9 min-w-11 rounded-full px-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-focus',
            current === lang ? 'bg-surface text-text shadow-sm' : 'text-muted',
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
