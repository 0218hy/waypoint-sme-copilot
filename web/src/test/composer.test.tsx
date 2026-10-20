import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Composer } from '@/chat/Composer'
import type { SpeechResultEvent } from '@/chat/speech'
import i18n from '@/i18n'

class FakeRecognition {
  static instances: FakeRecognition[] = []
  lang = ''
  interimResults = false
  continuous = false
  onresult: ((e: SpeechResultEvent) => void) | null = null
  onend: (() => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  start = vi.fn()
  stop = vi.fn(() => this.onend?.())
  abort = vi.fn()
  constructor() {
    FakeRecognition.instances.push(this)
  }
  /** Delivers results as the browser does: every result so far, the last one maybe interim. */
  say(...parts: [string, boolean][]) {
    const results = parts.map(([transcript, isFinal]) => Object.assign([{ transcript }], { isFinal }))
    act(() => this.onresult?.({ resultIndex: 0, results }))
  }
}

const last = () => FakeRecognition.instances.at(-1)!

beforeEach(() => {
  FakeRecognition.instances = []
  localStorage.clear()
  vi.stubGlobal('webkitSpeechRecognition', FakeRecognition)
})
afterEach(() => vi.unstubAllGlobals())

describe('composer voice input', () => {
  it('fills the textarea from speech and never sends by itself', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<Composer onSend={onSend} busy={false} />)
    const mic = screen.getByRole('button', { name: 'Voice input' })
    expect(mic).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByText(/speech service/)).toBeNull()

    await user.click(mic)
    const rec = last()
    expect(rec.start).toHaveBeenCalled()
    expect(rec.lang).toBe('en-SG')
    expect(rec.interimResults).toBe(true)
    expect(mic).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText("Your browser's own speech service turns your voice into text.")).toBeInTheDocument()

    rec.say(['near the', false])
    expect(screen.getByLabelText('Message Waypoint')).toHaveValue('near the')
    rec.say(['near the university', true])
    expect(screen.getByLabelText('Message Waypoint')).toHaveValue('near the university')
    expect(onSend).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(onSend).toHaveBeenCalledWith('near the university')
    expect(rec.abort).toHaveBeenCalled()
    expect(mic).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByLabelText('Message Waypoint')).toHaveValue('')
  })

  it('stops on a second tap, keeps typed text, and shows the hint only the first time', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<Composer onSend={vi.fn()} busy={false} />)
    await user.type(screen.getByLabelText('Message Waypoint'), 'Budget is')
    const mic = screen.getByRole('button', { name: 'Voice input' })
    await user.click(mic)
    last().say(['about 300k', false])
    expect(screen.getByLabelText('Message Waypoint')).toHaveValue('Budget is about 300k')
    await user.click(mic)
    expect(last().stop).toHaveBeenCalled()
    expect(mic).toHaveAttribute('aria-pressed', 'false')
    unmount()

    render(<Composer onSend={vi.fn()} busy={false} />)
    await user.click(screen.getByRole('button', { name: 'Voice input' }))
    expect(screen.queryByText(/speech service/)).toBeNull()
  })

  it('listens in Chinese when the UI is in Chinese', async () => {
    await i18n.changeLanguage('zh')
    const user = userEvent.setup()
    render(<Composer onSend={vi.fn()} busy={false} />)
    await user.click(screen.getByRole('button', { name: '语音输入' }))
    expect(last().lang).toBe('zh-CN')
  })

  it('hides the microphone when the browser has no speech recognition', () => {
    vi.unstubAllGlobals()
    render(<Composer onSend={vi.fn()} busy={false} />)
    expect(screen.queryByRole('button', { name: 'Voice input' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
  })
})
