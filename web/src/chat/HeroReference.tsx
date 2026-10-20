import { ArrowUpRight, BarChart3, CalendarRange, Coins, LayoutGrid, Map as MapIcon, Receipt, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/contracts/types'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/cn'
import { heroTitleKey, type HeroType } from './heroTitle'

const ICONS: Record<HeroType, LucideIcon> = {
  area_map: MapIcon,
  unit_compare: LayoutGrid,
  cost_breakdown: Receipt,
  setaside_slider: Coins,
  milestone_timeline: CalendarRange,
  plan_vs_actual: BarChart3,
}

/** One line that says what the card holds, from its payload and display text. */
function useSummary(w: Widget): string {
  const { t, i18n } = useTranslation()
  const p = w.payload
  const d = (id: string | null | undefined) => (id ? (w.display?.[id] ?? '') : '')
  switch (p.type) {
    case 'area_map':
      return p.top.map((id) => p.areas.find((a) => a.id === id)?.name ?? id).join(' · ')
    case 'unit_compare': {
      const chosen = p.units.find((u) => u.id === p.chosen)
      return chosen ? `${chosen.mall} ${chosen.unit_no}` : p.units.map((u) => u.mall).join(' · ')
    }
    case 'cost_breakdown':
      return t('canvas.costLine', { likely: d(p.total_likely), bad: d(p.total_bad) })
    case 'setaside_slider':
      return t('canvas.sliderLine', {
        share: new Intl.NumberFormat(i18n.language === 'zh' ? 'zh-CN' : 'en-SG', { style: 'percent', maximumFractionDigits: 0 }).format(p.share),
        open: d(p.open_likely),
      })
    case 'milestone_timeline': {
      const next = [...p.items].sort((a, b) => a.order - b.order).find((m) => m.status !== 'done')
      return next ? t('canvas.nextLine', { label: next.label, date: next.likely_date }) : ''
    }
    case 'plan_vs_actual':
      return t('w.plan_vs_actual.title')
    default:
      return ''
  }
}

/** Desktop chat: a compact stand-in for a hero widget that is (or can be) shown in the canvas. */
/** `replaced`: a newer card of the same kind exists (a past step's card is not an "earlier version"). */
export function HeroReference({ widget, shown, replaced, onShow }: { widget: Widget; shown: boolean; replaced: boolean; onShow: () => void }) {
  const { t } = useTranslation()
  const type = widget.payload.type as HeroType
  const Icon = ICONS[type]
  const summary = useSummary(widget)
  const title = t(heroTitleKey(type))
  return (
    <Card className={cn('transition-colors', shown ? 'border-accent bg-accent-soft/40' : 'hover:bg-surface-2')}>
      <button
        type="button"
        onClick={onShow}
        aria-pressed={shown}
        aria-label={shown ? t('canvas.shownAria', { title }) : t('canvas.showAria', { title })}
        className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-focus"
      >
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', shown ? 'bg-accent text-accent-fg' : 'bg-surface-2 text-accent')}>
          <Icon aria-hidden className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold leading-snug">{title}</span>
          {summary && <span className="block truncate text-sm text-muted">{summary}</span>}
          {replaced && <span className="block text-xs text-faint">{t('canvas.earlier')}</span>}
        </span>
        <span className={cn('inline-flex shrink-0 items-center gap-1 text-sm font-medium', shown ? 'text-accent' : 'text-muted')}>
          {shown ? t('canvas.shown') : t('canvas.show')}
          <ArrowUpRight aria-hidden className="size-4" />
        </span>
      </button>
    </Card>
  )
}
