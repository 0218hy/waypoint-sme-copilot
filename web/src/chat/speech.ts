// The browser's Web Speech API (SpeechRecognition), typed for what the composer uses.
// Not in TypeScript's DOM lib; Chrome and Safari expose it as webkitSpeechRecognition.

export interface SpeechResultEvent {
  resultIndex: number
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>
}

export interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: SpeechResultEvent) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start(): void
  stop(): void
  abort(): void
}

export type SpeechRecognitionCtor = new () => SpeechRecognitionLike

/** The SpeechRecognition constructor, or null when the browser has none. */
export function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

/** Recognition language for the UI language. */
export function speechLang(lng: string): string {
  return lng.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-SG'
}

const HINT_KEY = 'waypoint.voiceHintSeen'

/** True the first time voice input is used in this browser (then remembers it). */
export function firstVoiceUse(): boolean {
  try {
    if (localStorage.getItem(HINT_KEY)) return false
    localStorage.setItem(HINT_KEY, '1')
  } catch {
    // Storage blocked: show the hint each session rather than never.
  }
  return true
}
