import { ExternalLink, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Figure, SourceNote, Widget } from '@/contracts/types'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/cn'
import { figLabel, type LooseT } from './figLabel'
import { figText } from './figValues'

interface FigProps {
  widget: Widget
  id: string | null | undefined
  className?: string
  /** Show the small "i" icon after the text (default true). */
  icon?: boolean
}

/** A figure's display text, tappable for "Where's this from?". */
export function Fig({ widget, id, className, icon = true }: FigProps) {
  const { t } = useTranslation()
  const text = figText(widget, id)
  const figure = id ? widget.figures?.[id] : undefined
  if (text === undefined) {
    return <span className={cn('text-faint', className)}>{t('fig.missing')}</span>
  }
  if (!figure) return <span className={cn('tabular', className)}>{text}</span>
  const untrusted = figure.taint === 'untrusted'
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'tabular inline-flex items-baseline gap-0.5 rounded-sm text-left underline decoration-dotted decoration-1 underline-offset-4 hover:decoration-solid focus-visible:outline-2 focus-visible:outline-focus',
            untrusted ? 'decoration-warning' : 'decoration-faint',
            className,
          )}
          aria-label={t('fig.whereAria', { text })}
        >
          <span>{text}</span>
          {icon && <Info aria-hidden className="size-3 shrink-0 self-center text-faint" />}
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <FigureSource figure={figure} text={text} />
      </PopoverContent>
    </Popover>
  )
}

export function FigureSource({ figure, text }: { figure: Figure; text?: string }) {
  const { t } = useTranslation()
  const s = figure.source
  const label = figLabel(t as unknown as LooseT, figure.id, figure.label)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-faint">{t('fig.where')}</p>
          <p className="font-medium">{label}</p>
          {text && <p className="tabular text-lg font-semibold">{text}</p>}
        </div>
        {s.kind === 'simulated' && <Badge tone="warning">{t('fig.simulated')}</Badge>}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t('fig.kind')}</dt>
        <dd>{t(`sourceKind.${s.kind}`)}</dd>
        <dt className="text-muted">{t('fig.ref')}</dt>
        <dd className="break-words font-mono text-xs leading-6">{s.ref}</dd>
        {s.as_of && (
          <>
            <dt className="text-muted">{t('fig.asOf')}</dt>
            <dd>{s.as_of}</dd>
          </>
        )}
      </dl>
      {s.note && <p className="text-sm text-muted">{s.note}</p>}
      {s.url && (
        <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-accent underline">
          {t('fig.openSource')} <ExternalLink aria-hidden className="size-3" />
        </a>
      )}
      {figure.assumptions && figure.assumptions.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted">{t('fig.assumptions')}</p>
          <ul className="mt-1 flex flex-wrap gap-1">
            {figure.assumptions.map((a) => (
              <li key={a}>
                <code className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">{a}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
      {figure.taint === 'untrusted' && (
        <p className="rounded-lg bg-warning-soft px-2 py-1.5 text-sm text-warning">{t('fig.untrusted')}</p>
      )}
    </div>
  )
}

/** A dated source line (SourceNote) with an optional link. */
const KIND_KEY = { law: 'law', design: 'design', 'law+design': 'both' } as const

/** "Law", "Design rule" or "Law + design rule" for a rule or legal note (rules/rules.yaml `kind`). */
export function SourceKindBadge({ kind }: { kind: NonNullable<SourceNote['kind']> }) {
  const { t } = useTranslation()
  return (
    <Badge tone={kind === 'design' ? 'info' : 'accent'} data-kind={kind}>
      {t(`fig.sourceKind.${KIND_KEY[kind]}`)}
    </Badge>
  )
}

export function SourceLine({ source, className }: { source: SourceNote; className?: string }) {
  const { t } = useTranslation()
  const body = (
    <>
      {source.label}
      {source.as_of && <span className="text-faint"> · {t('fig.asOfShort', { date: source.as_of })}</span>}
    </>
  )
  return (
    <p className={cn('text-xs text-muted', className)}>
      {source.kind && (
        <>
          <SourceKindBadge kind={source.kind} />{' '}
        </>
      )}
      <span className="text-faint">{t('fig.source')}: </span>
      {source.url ? (
        <a href={source.url} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted underline-offset-2 hover:text-text">
          {body}
        </a>
      ) : (
        body
      )}
    </p>
  )
}

/** A popover button for a SourceNote (cost lines, rules). */
export function SourcePopover({ source, label }: { source: SourceNote; label?: string }) {
  const { t } = useTranslation()
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex min-h-8 items-center gap-1 rounded-md px-1 text-xs text-muted underline decoration-dotted underline-offset-2 hover:text-text focus-visible:outline-2 focus-visible:outline-focus"
          aria-label={label ? t('fig.whereAria', { text: label }) : t('fig.where')}
        >
          <Info aria-hidden className="size-3" />
          {t('fig.whereShort')}
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <p className="text-xs font-medium uppercase tracking-wide text-faint">{t('fig.where')}</p>
        {label && <p className="font-medium">{label}</p>}
        <SourceLine source={source} className="mt-1 text-sm" />
      </PopoverContent>
    </Popover>
  )
}
