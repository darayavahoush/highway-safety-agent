// Keyboard shortcuts, kept pure so they can be tested without a browser.
//
//   ?  (or A)      open or close the About window
//   G then 1 to 5  go to a page (Overview, Corridor, Incidents, Activity, System status)
//   H              back to the home page
//   Esc            close About, or leave the control room
//
// Page jumps use a two-key "G then number" chord so they never clash with 1 to 4,
// which switch tabs on the Corridor page.

export const CHORD_MS = 1200
export const PAGE_KEYS = ['control', 'corridor', 'incidents', 'activity', 'system']

const TYPING = 'input, textarea, select, [contenteditable="true"], [contenteditable=""]'

export const isTypingTarget = (t) => !!t?.matches?.(TYPING)
export const hasModifier = (e) => e.ctrlKey || e.metaKey || e.altKey

// Returns { action, chord }. `chord` is the pending-G state to carry to the next key press.
export function resolveShortcut(e, { chordAt = null, now = Date.now(), page = 'home', aboutOpen = false } = {}) {
  const none = { action: null, chord: null }
  if (e.defaultPrevented || e.isComposing) return none
  if (isTypingTarget(e.target) || hasModifier(e)) return none // keeps Cmd+A, Ctrl+R and friends working

  const key = e.key
  if (key === 'Escape') {
    if (aboutOpen) return { action: { type: 'about', open: false }, chord: null }
    if (page === 'control') return { action: { type: 'page', page: 'home' }, chord: null }
    return none
  }
  if (key === '?' || key === 'a' || key === 'A') return { action: { type: 'about', open: !aboutOpen }, chord: null }
  if (aboutOpen) return none

  const pending = chordAt != null && now - chordAt <= CHORD_MS
  if (pending && /^[1-5]$/.test(key) && page !== 'home') {
    return { action: { type: 'page', page: PAGE_KEYS[Number(key) - 1] }, chord: null, consume: true }
  }
  if ((key === 'g' || key === 'G') && page !== 'home') return { action: null, chord: now }
  if ((key === 'h' || key === 'H') && page !== 'home') return { action: { type: 'page', page: 'home' }, chord: null }
  return none
}
