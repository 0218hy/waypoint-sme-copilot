import { zodResolver } from '@hookform/resolvers/zod'
import { Building2, Loader2, MailCheck } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { api, type DemoInfo } from '@/lib/api'

export function SignIn({ demo, onSignedIn }: { demo: DemoInfo | null; onSignedIn: () => void }) {
  const { t, i18n } = useTranslation()
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [ssoBusy, setSsoBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const schema = z.object({ email: z.string().trim().email(t('auth.badEmail')) })
  const { register, handleSubmit, formState } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { email: '' } })

  const submit = handleSubmit(async ({ email }) => {
    setError(null)
    try {
      await api.requestLink(email, i18n.language)
      setSentTo(email)
    } catch {
      setError(t('auth.linkError'))
    }
  })

  const sso = async () => {
    setError(null)
    setSsoBusy(true)
    try {
      const { token } = await api.demoSsoToken()
      await api.webankSso(token, i18n.language)
      onSignedIn()
    } catch {
      setError(t('auth.ssoError'))
    } finally {
      setSsoBusy(false)
    }
  }

  const err = formState.errors.email?.message
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t('auth.title')}</h1>
        <p className="mt-1 text-muted">{t('auth.subtitle')}</p>
      </div>
      <Card className="p-4">
        {sentTo ? (
          <div role="status" className="flex flex-col items-start gap-3">
            <MailCheck aria-hidden className="size-8 text-accent" />
            <h2 className="text-lg font-semibold">{t('auth.checkInbox')}</h2>
            <p className="text-muted">{t('auth.sentTo', { email: sentTo })}</p>
            {demo && (
              <a href={demo.mailpit_url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-accent underline">
                {t('auth.openMailpit')}
              </a>
            )}
            <Button variant="ghost" size="sm" onClick={() => setSentTo(null)}>
              {t('auth.useAnother')}
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="flex flex-col gap-3">
            <label htmlFor="email" className="text-sm font-medium">
              {t('auth.email')}
            </label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="joonrui@example.com"
              aria-invalid={!!err}
              aria-describedby={err ? 'email-err' : 'email-hint'}
              {...register('email')}
            />
            {err ? (
              <p id="email-err" role="alert" className="text-sm text-danger">
                {err}
              </p>
            ) : (
              <p id="email-hint" className="text-xs text-muted">
                {t('auth.hint')}
              </p>
            )}
            <Button type="submit" size="lg" disabled={formState.isSubmitting}>
              {formState.isSubmitting && <Loader2 aria-hidden className="animate-spin" />}
              {t('auth.sendLink')}
            </Button>
          </form>
        )}
      </Card>
      {demo && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3 text-xs text-faint">
            <span className="h-px flex-1 bg-border" />
            {t('auth.or')}
            <span className="h-px flex-1 bg-border" />
          </div>
          <Button variant="secondary" size="lg" onClick={() => void sso()} disabled={ssoBusy}>
            {ssoBusy ? <Loader2 aria-hidden className="animate-spin" /> : <Building2 aria-hidden />}
            {t('auth.webank')}
          </Button>
          <p className="text-center text-xs text-muted">{t('auth.webankNote')}</p>
        </div>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
    </main>
  )
}
