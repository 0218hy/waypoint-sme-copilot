import { Loader2 } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AccountTab } from '@/account/AccountTab'
import i18n from '@/i18n'
import { SignIn } from '@/auth/SignIn'
import { ChatProvider } from '@/chat/ChatProvider'
import { useChat } from '@/chat/chatContext'
import { ChatTab } from '@/chat/ChatTab'
import { ErrorState } from '@/components/ErrorState'
import { DocumentsTab } from '@/documents/DocumentsTab'
import { GoalTab } from '@/goal/GoalTab'
import { api, ApiError, type DemoInfo, type Lang, type SessionResponse } from '@/lib/api'
import { tabFromPath, useHashRoute, type Tab } from '@/lib/route'
import { TopBar } from '@/shell/TopBar'
import { defaultWidgetEnv, WidgetEnvContext, type WidgetEnv } from '@/widgets/env'

const Gallery = import.meta.env.DEV ? lazy(() => import('@/dev/Gallery')) : null

export default function App() {
  const [path] = useHashRoute()
  if (Gallery && path.startsWith('/dev/widgets')) {
    return (
      <Suspense fallback={<Splash />}>
        <Gallery />
      </Suspense>
    )
  }
  return <Main />
}

type SessionState = { status: 'loading' } | { status: 'error'; error: string } | { status: 'ready'; session: SessionResponse }

function Main() {
  const { t } = useTranslation()
  const langAppliedFor = useRef<string | null>(null)
  const [session, setSession] = useState<SessionState>({ status: 'loading' })
  const [demo, setDemo] = useState<DemoInfo | null>(null)

  const loadSession = useCallback(() => {
    api.session().then(
      (s) => {
        // The account's language wins once per sign-in; later toggles PATCH it.
        if (s.user?.lang && s.user.id !== langAppliedFor.current) {
          langAppliedFor.current = s.user.id
          void i18n.changeLanguage(s.user.lang)
        }
        setSession({ status: 'ready', session: s })
      },
      (e: unknown) =>
        e instanceof ApiError && e.status === 401
          ? setSession({ status: 'ready', session: { user: null, state: null } })
          : setSession({ status: 'error', error: e instanceof Error ? e.message : String(e) }),
    )
  }, [])

  useEffect(() => {
    loadSession()
    api.demoInfo().then(
      (d) => setDemo(d?.mailpit_url ? d : null),
      () => setDemo(null),
    )
  }, [loadSession])

  const saveLang = useCallback((lang: Lang) => {
    api.patchAccount({ lang }).catch(() => undefined)
  }, [])

  if (session.status === 'loading') return <Splash />
  if (session.status === 'error') {
    return (
      <div className="flex min-h-dvh flex-col">
        <TopBar demo={demo} />
        <main className="mx-auto w-full max-w-md p-4">
          <ErrorState message={t('shell.offline')} onRetry={loadSession} />
        </main>
      </div>
    )
  }
  const { user, state } = session.session
  if (!user) {
    return (
      <div className="flex min-h-dvh flex-col">
        <TopBar demo={demo} />
        <SignIn demo={demo} onSignedIn={loadSession} />
      </div>
    )
  }
  return (
    <ChatProvider threadId={state?.journey_id ?? user.id} initialState={state} onUnauthorized={loadSession}>
      <Shell demo={demo} onSignedOut={loadSession} onLang={saveLang} />
    </ChatProvider>
  )
}

function Shell({ demo, onSignedOut, onLang }: { demo: DemoInfo | null; onSignedOut: () => void; onLang: (l: Lang) => void }) {
  const { t } = useTranslation()
  const [path, go] = useHashRoute()
  const tab = tabFromPath(path)
  const chat = useChat()
  const openTab = useCallback((id: Tab) => go(`/${id}`), [go])
  const env = useMemo<WidgetEnv>(
    () => ({ ...defaultWidgetEnv, openTab, sampleQuote: demo ? api.demoSampleQuote : undefined }),
    [openTab, demo],
  )

  // A goal appearing (approval) opens the Goal tab once.
  const goalId = chat.journey?.goal_id ?? null
  const seenGoal = useRef(goalId)
  useEffect(() => {
    if (goalId && goalId !== seenGoal.current) {
      if (seenGoal.current === null) openTab('goal')
      seenGoal.current = goalId
    }
  }, [goalId, openTab])

  return (
    <WidgetEnvContext.Provider value={env}>
      <div className="fixed inset-0 flex flex-col">
        <TopBar demo={demo} tab={tab} onTab={openTab} onLang={onLang} />
        {tab === 'chat' ? (
          <main className="flex min-h-0 flex-1 flex-col" aria-label={t('tabs.chat')}>
            <ChatTab demo={!!demo} />
          </main>
        ) : (
          <main className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-2xl px-3 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] lg:max-w-6xl lg:px-6 lg:py-6">
              {tab === 'goal' && <GoalTab onOpenChat={() => openTab('chat')} />}
              {tab === 'documents' && <DocumentsTab />}
              {tab === 'account' && <AccountTab demo={demo} onSignedOut={onSignedOut} onLang={onLang} />}
            </div>
          </main>
        )}
      </div>
    </WidgetEnvContext.Provider>
  )
}

function Splash() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Loading">
      <Loader2 aria-hidden className="size-6 animate-spin text-accent motion-reduce:animate-none" />
    </div>
  )
}
