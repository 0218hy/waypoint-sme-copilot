import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import i18n from '@/i18n'

// jsdom lacks these browser APIs.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList
}
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= function () {}
Element.prototype.scrollTo ??= function () {}
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => undefined

// ECharts needs real layout; tests check the text around charts instead.
vi.mock('@/charts/EChart', async () => {
  const React = await import('react')
  return { EChart: ({ label }: { label: string }) => React.createElement('div', { role: 'img', 'aria-label': label }) }
})

afterEach(async () => {
  cleanup()
  await i18n.changeLanguage('en')
})
