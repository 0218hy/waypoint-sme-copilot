import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en'
import zh from './zh'

export const resources = { en: { translation: en }, zh: { translation: zh } } as const

function initialLang(): 'en' | 'zh' {
  const nav = typeof navigator !== 'undefined' ? navigator.language : 'en'
  return nav.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

void i18n.use(initReactI18next).init({
  resources,
  lng: initialLang(),
  fallbackLng: 'en',
  supportedLngs: ['en', 'zh'],
  interpolation: { escapeValue: false },
  returnNull: false,
})

const setLang = (lng: string) => {
  if (typeof document !== 'undefined') document.documentElement.lang = lng === 'zh' ? 'zh-CN' : 'en'
}
setLang(i18n.language)
i18n.on('languageChanged', setLang)

export default i18n
