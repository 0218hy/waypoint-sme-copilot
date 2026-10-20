import { Check, Download, Loader2, LogOut, ShieldOff, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DemoControls } from '@/components/DemoControls'
import { ErrorState } from '@/components/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { api, type Account, type CheckinFrequency, type DemoInfo, type Lang } from '@/lib/api'
import { cn } from '@/lib/cn'
import { applyTheme, getThemePref, type ThemePref } from '@/lib/theme'
import { useApi } from '@/lib/useApi'

const FREQS: CheckinFrequency[] = ['weekly', 'fortnightly', 'monthly']

export function AccountTab({ demo, onSignedOut, onLang }: { demo: DemoInfo | null; onSignedOut: () => void; onLang: (l: Lang) => void }) {
  const { t, i18n } = useTranslation()
  const [state, reload, set] = useApi(() => api.account())
  const [saving, setSaving] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [confirmWithdraw, setConfirmWithdraw] = useState(false)
  const [theme, setTheme] = useState<ThemePref>(getThemePref)
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (state.status === 'loading') return <Skeleton className="h-80 w-full" />
  if (state.status === 'error') return <ErrorState message={t('account.loadError')} onRetry={reload} />
  const acc = state.data

  const patch = async (key: string, p: Partial<Pick<Account, 'lang' | 'checkin_frequency' | 'email_amounts'>>) => {
    setSaving(key)
    setSaveError(null)
    const prev = acc
    set({ ...acc, ...p })
    try {
      const next = await api.patchAccount(p)
      if (next) set(next)
      setSaved(key)
      setTimeout(() => setSaved((s) => (s === key ? null : s)), 1500)
    } catch {
      set(prev)
      setSaveError(t('account.saveError'))
    } finally {
      setSaving(null)
    }
  }

  const status = (key: string) =>
    saving === key ? (
      <Loader2 aria-label={t('account.saving')} className="size-4 animate-spin text-muted motion-reduce:animate-none" />
    ) : saved === key ? (
      <span role="status" className="inline-flex items-center gap-1 text-xs text-success">
        <Check aria-hidden className="size-3" />
        {t('account.saved')}
      </span>
    ) : null

  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-2 lg:items-start lg:gap-6">
      <div className="flex flex-col gap-4">
      <Card className="divide-y divide-border">
        <Row label={t('account.email')}>
          <span className="break-all">{acc.email ?? t('account.noEmail')}</span>
        </Row>
        <Row label={t('account.signIn')}>
          {acc.host_mode === 'embedded' ? t('account.viaWebank') : t('account.viaEmail')}
        </Row>
      </Card>

      <Card className="flex flex-col divide-y divide-border">
        <Setting label={t('account.language')} status={status('lang')}>
          <Segmented
            label={t('account.language')}
            value={i18n.language === 'zh' ? 'zh' : 'en'}
            options={[
              ['en', 'English'],
              ['zh', '中文'],
            ]}
            onChange={(v) => {
              void i18n.changeLanguage(v)
              onLang(v as Lang)
              void patch('lang', { lang: v as Lang })
            }}
          />
        </Setting>
        <Setting label={t('account.frequency')} hint={t('account.frequencyHint')} status={status('freq')}>
          <Segmented
            label={t('account.frequency')}
            value={acc.checkin_frequency}
            options={FREQS.map((f) => [f, t(`account.freq.${f}`)])}
            onChange={(v) => void patch('freq', { checkin_frequency: v as CheckinFrequency })}
          />
        </Setting>
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <div>
            <label htmlFor="email-amounts" className="font-medium">
              {t('account.amounts')}
            </label>
            <p className="text-sm text-muted">{t('account.amountsHint')}</p>
          </div>
          <div className="flex items-center gap-2">
            {status('amounts')}
            <Switch id="email-amounts" checked={acc.email_amounts} onCheckedChange={(v) => void patch('amounts', { email_amounts: v })} />
          </div>
        </div>
        <Setting label={t('account.theme')} hint={t('account.themeHint')}>
          <Segmented
            label={t('account.theme')}
            value={theme}
            options={[
              ['system', t('account.themeSystem')],
              ['light', t('account.themeLight')],
              ['dark', t('account.themeDark')],
            ]}
            onChange={(v) => {
              setTheme(v as ThemePref)
              applyTheme(v as ThemePref)
            }}
          />
        </Setting>
      </Card>
      {saveError && (
        <p role="alert" className="text-sm text-danger">
          {saveError}
        </p>
      )}

      </div>
      <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-semibold">{t('account.consent')}</h2>
          {acc.consent?.granted ? <Badge tone="success">{t('account.consentOn')}</Badge> : <Badge>{t('account.consentOff')}</Badge>}
        </div>
        {acc.consent?.reads && acc.consent.reads.length > 0 && (
          <ul className="list-disc pl-5 text-sm text-muted">
            {acc.consent.reads.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
        <p className="text-sm text-muted">{t('account.consentNote')}</p>
        {acc.consent?.granted &&
          (confirmWithdraw ? (
            <div className="flex flex-col gap-2 rounded-xl bg-danger-soft/60 p-3" role="alertdialog" aria-label={t('account.withdrawConfirm')}>
              <p className="text-sm">{t('account.withdrawConfirm')}</p>
              <div className="flex gap-2">
                <Button
                  variant="danger"
                  size="sm"
                  onClick={async () => {
                    try {
                      await api.withdrawConsent()
                      setConfirmWithdraw(false)
                      reload()
                    } catch {
                      setSaveError(t('account.saveError'))
                    }
                  }}
                >
                  {t('account.withdrawYes')}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirmWithdraw(false)}>
                  {t('common.cancel')}
                </Button>
              </div>
            </div>
          ) : (
            <Button variant="danger" className="self-start" onClick={() => setConfirmWithdraw(true)}>
              <ShieldOff aria-hidden />
              {t('account.withdraw')}
            </Button>
          ))}
      </Card>

      <Card className="flex flex-col gap-3 p-4">
        <h2 className="font-semibold">{t('account.data')}</h2>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" asChild>
            <a href={api.exportUrl} download="waypoint-export.json">
              <Download aria-hidden />
              {t('account.export')}
            </a>
          </Button>
          {!confirmDelete && (
            <Button variant="danger" onClick={() => setConfirmDelete(true)}>
              <Trash2 aria-hidden />
              {t('account.delete')}
            </Button>
          )}
        </div>
        {confirmDelete && (
          <div className="flex flex-col gap-2 rounded-xl bg-danger-soft/60 p-3" role="alertdialog" aria-label={t('account.deleteConfirm')}>
            <p className="text-sm">{t('account.deleteConfirm')}</p>
            <div className="flex gap-2">
              <Button
                variant="danger"
                size="sm"
                onClick={async () => {
                  try {
                    await api.deleteAccount()
                    onSignedOut()
                  } catch {
                    setSaveError(t('account.saveError'))
                  }
                }}
              >
                {t('account.deleteYes')}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                {t('common.cancel')}
              </Button>
            </div>
          </div>
        )}
      </Card>

      {demo && (
        <Card className="p-4">
          <DemoControls />
        </Card>
      )}

      <Button
        variant="secondary"
        size="lg"
        onClick={async () => {
          try {
            await api.logout()
          } finally {
            onSignedOut()
          }
        }}
      >
        <LogOut aria-hidden />
        {t('account.signOut')}
      </Button>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  )
}

function Setting({ label, hint, status, children }: { label: string; hint?: string; status?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{label}</span>
        {status}
      </div>
      {hint && <p className="-mt-1 text-sm text-muted">{hint}</p>}
      {children}
    </div>
  )
}

function Segmented({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-xl bg-surface-2 p-1">
      {options.map(([v, l]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => value !== v && onChange(v)}
          className={cn(
            'min-h-10 flex-1 rounded-lg px-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-focus',
            value === v ? 'bg-surface text-text shadow-sm' : 'text-muted',
          )}
        >
          {l}
        </button>
      ))}
    </div>
  )
}
