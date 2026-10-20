import { useTranslation } from 'react-i18next'
import { Fig } from '@/components/Fig'
import { latestOf, type ToolEntry } from './transcript'

/** Desktop rail: the decisions so far, read from the latest widgets' display values (read-only). */
export function PlanSoFar({ entries }: { entries: ToolEntry[] }) {
  const { t, i18n } = useTranslation()
  const units = latestOf(entries, 'unit_compare')
  const site = latestOf(entries, 'plan_summary')
  const areaCard = latestOf(entries, 'area_card')
  const confirm = latestOf(entries, 'confirm_card')
  const siteConfirm = confirm?.payload.step === 'site' ? confirm : undefined
  const cost = latestOf(entries, 'cost_breakdown')
  const slider = latestOf(entries, 'setaside_slider')

  const chosen = units?.payload.chosen ? units.payload.units.find((u) => u.id === units.payload.chosen) : undefined
  const siteSummary = site && site.payload.kind === 'site' ? site : undefined
  const where = chosen ? (
    <>
      {chosen.mall} {chosen.unit_no}
      <span className="block text-xs font-normal text-muted">{chosen.area_name}</span>
    </>
  ) : siteSummary ? (
    siteSummary.payload.title
  ) : siteConfirm ? (
    siteConfirm.payload.title
  ) : areaCard ? (
    areaCard.payload.name
  ) : null

  const rows: { key: string; label: string; value: React.ReactNode }[] = [
    { key: 'where', label: t('plan.where'), value: where },
    {
      key: 'cost',
      label: t('plan.cost'),
      value: cost ? (
        <>
          <Fig widget={cost} id={cost.payload.total_likely} />
          <span className="block text-xs font-normal text-muted">{cost.display?.[cost.payload.total_likely_cny]}</span>
        </>
      ) : null,
    },
    {
      key: 'share',
      label: t('plan.share'),
      value: slider ? (
        <>
          {/* The committed share itself (opened_share is the chance of opening, not the share). */}
          {pct(slider.payload.share, i18n.language)}
          <span className="block text-xs font-normal text-muted">{slider.display?.[slider.payload.monthly_amount]}</span>
        </>
      ) : null,
    },
    { key: 'open', label: t('plan.open'), value: slider ? <Fig widget={slider} id={slider.payload.open_likely} /> : null },
  ]
  return (
    <section aria-labelledby="plan-so-far" className="rounded-2xl border border-border bg-surface p-3">
      <h2 id="plan-so-far" className="text-xs font-semibold uppercase tracking-wide text-faint">
        {t('plan.title')}
      </h2>
      <dl className="mt-2 flex flex-col gap-2.5">
        {rows.map((r) => (
          <div key={r.key}>
            <dt className="text-xs text-muted">{r.label}</dt>
            <dd className="text-sm font-semibold">{r.value ?? <span className="font-normal text-faint">{t('plan.notYet')}</span>}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function pct(v: number, lang: string): string {
  return new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-SG', { style: 'percent', maximumFractionDigits: 0 }).format(v)
}
