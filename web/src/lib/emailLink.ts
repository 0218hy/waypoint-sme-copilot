/**
 * Links from Waypoint's emails (docs/INTERFACES.md §1): the check-in email's "Something changed"
 * (`?checkin=<signed token>`, or `?checkin=recorded|already|expired` where the one-tap link lands) and
 * the alert email's link (`?alert=<id>`).
 *
 * The parameter is read once, at start-up, then cleared from the address bar. It is kept until the
 * chat's opening run sends it to the server (which checks it), so it survives the sign-in page and
 * the magic-link redirect in the same browser. The server decides what it opens; nothing is trusted here.
 */
export type EmailLinkKind = 'checkin' | 'alert'
export interface EmailLink {
  kind: EmailLinkKind
  value: string
}

const KINDS: readonly EmailLinkKind[] = ['checkin', 'alert']
const KEY = 'waypoint.emailLink'
const TTL_MS = 30 * 60 * 1000 // long enough to sign in by email
let held: (EmailLink & { at: number }) | null = null

/** Read `?checkin=` / `?alert=` once, keep it, and clear it from the URL (opening the chat tab). */
export function captureEmailLink(loc: Location = window.location, history: History = window.history): EmailLink | null {
  const params = new URLSearchParams(loc.search)
  let link: EmailLink | null = null
  for (const kind of KINDS) {
    const value = params.get(kind)
    if (value && !link) link = { kind, value: value.slice(0, 512) }
    params.delete(kind)
  }
  if (!link) return null
  held = { ...link, at: Date.now() }
  try {
    localStorage.setItem(KEY, JSON.stringify(held))
  } catch {
    /* storage blocked: the in-memory copy still covers a sign-in without a reload */
  }
  const qs = params.toString()
  history.replaceState(history.state, '', `${loc.pathname}${qs ? `?${qs}` : ''}#/chat`)
  return link
}

/** The kept link, once: the next call returns null. Links older than half an hour are dropped. */
export function takeEmailLink(now: number = Date.now()): EmailLink | null {
  let got = held
  held = null
  try {
    const raw = localStorage.getItem(KEY)
    localStorage.removeItem(KEY)
    if (!got && raw) got = JSON.parse(raw) as EmailLink & { at: number }
  } catch {
    /* unreadable: ignore */
  }
  if (!got || !KINDS.includes(got.kind) || typeof got.value !== 'string' || now - Number(got.at) > TTL_MS) return null
  return { kind: got.kind, value: got.value }
}
