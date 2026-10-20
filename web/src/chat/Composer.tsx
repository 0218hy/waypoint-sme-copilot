import { ArrowUp, Mic } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/cn'
import { firstVoiceUse, getSpeechRecognition, speechLang, type SpeechRecognitionLike } from './speech'

const MAX_HEIGHT = 128

export function Composer({ onSend, busy }: { onSend: (text: string) => void; busy: boolean }) {
  const { t, i18n } = useTranslation()
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)
  const [Speech] = useState(getSpeechRecognition)
  const recRef = useRef<SpeechRecognitionLike | null>(null)
  const [listening, setListening] = useState(false)
  const [showHint, setShowHint] = useState(false)

  const fit = () => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }

  /** Ends recognition. `discard` drops any words still on their way (used on send). */
  const stopListening = (discard: boolean) => {
    const rec = recRef.current
    if (!rec) return
    recRef.current = null
    if (discard) {
      rec.onresult = null
      rec.abort()
    } else {
      rec.stop()
    }
    setListening(false)
  }

  useEffect(
    () => () => {
      const rec = recRef.current
      if (!rec) return
      rec.onresult = rec.onend = rec.onerror = null
      rec.abort()
    },
    [],
  )

  const startListening = () => {
    if (!Speech) return
    const rec = new Speech()
    rec.lang = speechLang(i18n.language)
    rec.interimResults = true
    rec.continuous = true
    const base = text.trimEnd()
    const sep = base && !rec.lang.startsWith('zh') ? ' ' : ''
    rec.onresult = (e) => {
      const said = Array.from(e.results, (r) => r[0]?.transcript ?? '').join('').trim()
      setText(said ? base + sep + said : base)
      requestAnimationFrame(fit)
    }
    const done = () => {
      if (recRef.current === rec) recRef.current = null
      setListening(false)
    }
    rec.onend = done
    rec.onerror = done
    recRef.current = rec
    try {
      rec.start()
    } catch {
      done()
      return
    }
    setListening(true)
    if (firstVoiceUse()) setShowHint(true)
    ref.current?.focus()
  }

  const send = () => {
    const v = text.trim()
    if (!v || busy) return
    stopListening(true)
    setShowHint(false)
    onSend(v)
    setText('')
    requestAnimationFrame(() => {
      if (ref.current) ref.current.style.height = ''
    })
  }

  return (
    <form
      className="border-t border-border bg-surface px-3 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]"
      onSubmit={(e) => {
        e.preventDefault()
        send()
      }}
    >
      <div className="mx-auto flex max-w-2xl items-end gap-2">
        <label htmlFor="composer" className="sr-only">
          {t('chat.composerLabel')}
        </label>
        <textarea
          id="composer"
          ref={ref}
          rows={1}
          value={text}
          enterKeyHint="send"
          placeholder={listening ? t('chat.listening') : t('chat.placeholder')}
          onChange={(e) => {
            setText(e.target.value)
            fit()
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              send()
            }
          }}
          className="max-h-32 min-h-11 flex-1 resize-none rounded-2xl border border-border-strong bg-surface-2 px-4 py-2.5 text-[16px] leading-6 placeholder:text-faint focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus"
        />
        {Speech && (
          <Button
            variant={listening ? 'soft' : 'ghost'}
            size="icon"
            className={cn('rounded-full', listening && 'animate-pulse motion-reduce:animate-none')}
            aria-label={t('chat.voice')}
            aria-pressed={listening}
            title={t('chat.voice')}
            onClick={() => (listening ? stopListening(false) : startListening())}
          >
            <Mic aria-hidden className="size-5!" />
          </Button>
        )}
        <Button type="submit" size="icon" className="rounded-full" disabled={busy || !text.trim()} aria-label={t('chat.send')}>
          <ArrowUp aria-hidden className="size-5!" />
        </Button>
      </div>
      <p className="sr-only" role="status" aria-live="polite">
        {listening ? t('chat.listening') : ''}
      </p>
      {showHint && <p className="mx-auto mt-1 max-w-2xl px-1 text-xs text-faint">{t('chat.voiceHint')}</p>}
    </form>
  )
}
