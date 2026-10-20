import { Inbox } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import type { DemoInfo, Lang } from '@/lib/api'
import { cn } from '@/lib/cn'
import { TABS, type Tab } from '@/lib/route'
import { LanguageToggle } from './LanguageToggle'
import { Wordmark } from './Wordmark'

interface Props {
  demo: DemoInfo | null
  tab?: Tab
  onTab?: (tab: Tab) => void
  onLang?: (lang: Lang) => void
}

export function TopBar({ demo, tab, onTab, onLang }: Props) {
  const { t } = useTranslation()
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 pt-[env(safe-area-inset-top)] backdrop-blur">
      <div className="mx-auto flex max-w-2xl items-center justify-between gap-2 px-3 py-2 lg:max-w-none lg:gap-6 lg:px-6">
        <Wordmark />
        {tab && onTab && <TabLinks tab={tab} onTab={onTab} className="hidden flex-1 lg:flex" />}
        <div className="flex items-center gap-1.5">
          {demo && (
            <>
              <Badge tone="warning" title={t('shell.demoHint')}>
                {t('shell.demo')}
              </Badge>
              <a
                href={demo.mailpit_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-9 items-center gap-1 rounded-full px-2 text-sm font-medium text-accent hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-focus"
              >
                <Inbox aria-hidden className="size-4" />
                <span>{t('shell.inbox')}</span>
              </a>
            </>
          )}
          <LanguageToggle onChange={onLang} />
        </div>
      </div>
      {tab && onTab && <TabLinks tab={tab} onTab={onTab} className="mx-auto flex max-w-2xl px-2 lg:hidden" />}
    </header>
  )
}

function TabLinks({ tab, onTab, className }: { tab: Tab; onTab: (tab: Tab) => void; className?: string }) {
  const { t } = useTranslation()
  return (
    <nav aria-label={t('shell.tabs')} className={className}>
      <ul className="flex flex-1 lg:flex-none lg:gap-1">
        {TABS.map((id) => (
          <li key={id} className="flex-1 lg:flex-none">
            <a
              href={`#/${id}`}
              aria-current={tab === id ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault()
                onTab(id)
              }}
              className={cn(
                'flex min-h-11 items-center justify-center border-b-2 text-sm font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus lg:min-h-10 lg:rounded-lg lg:border-b-0 lg:px-3',
                tab === id ? 'border-accent text-text lg:bg-accent-soft lg:text-accent' : 'border-transparent text-muted hover:text-text lg:hover:bg-surface-2',
              )}
            >
              {t(`tabs.${id}`)}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
