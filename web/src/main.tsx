import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './i18n'
import './index.css'
import { captureEmailLink } from './lib/emailLink'
import { applyTheme, getThemePref } from './lib/theme'

applyTheme(getThemePref())
captureEmailLink() // ?checkin= / ?alert= from an email: read once, then cleared from the address bar

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
