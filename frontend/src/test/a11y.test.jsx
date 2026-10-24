import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import axe from 'axe-core'
import App from '../App.jsx'
import AboutModal from '../components/AboutModal.jsx'
import LiveAnnouncer, { announcement } from '../components/LiveAnnouncer.jsx'

afterEach(cleanup)
const wait = (ms = 400) => act(async () => { await new Promise((r) => setTimeout(r, ms)) })
const nav = (l) => [...document.querySelectorAll('.ops-nav-link')].find((b) => b.textContent.includes(l))

describe('axe finds no structural violations on any page', () => {
  it('home, every control-room page, and the About dialog', async () => {
    render(<App />); await wait()
    const check = async (name) => {
      const r = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } }) // jsdom has no layout
      expect(r.violations.map((v) => `${name}: ${v.id} ${v.nodes[0].target.join(' ')}`)).toEqual([])
    }
    await check('home')
    fireEvent.click(screen.getAllByRole('button', { name: /enter|open|control room|launch|start/i })[0]); await wait()
    for (const l of ['Overview', 'Corridor', 'Incidents', 'Activity', 'System status']) { fireEvent.click(nav(l)); await wait(); await check(l) }
    fireEvent.keyDown(window, { key: '?' }); await wait(); await check('about')
  }, 60000)
})

describe('About dialog focus', () => {
  it('takes focus on open, traps Tab, and returns focus on close', () => {
    const opener = document.createElement('button'); document.body.appendChild(opener); opener.focus()
    const { rerender } = render(<AboutModal isOpen onClose={() => {}} />)
    const dlg = screen.getByRole('dialog', { name: /about highway safety agent/i })
    expect(dlg.contains(document.activeElement)).toBe(true)
    // Tab from the last control wraps to the first; Shift+Tab from the first wraps to the last.
    const items = [...dlg.querySelectorAll('a[href], button, summary')].filter(Boolean)
    items.at(-1).focus(); fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(items[0])
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(dlg.contains(document.activeElement)).toBe(true)
    rerender(<AboutModal isOpen={false} onClose={() => {}} />)
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
})

describe('screen-reader announcements', () => {
  const mk = (id, severity = 'P0', status = 'detected') => ({ id, severity, status, type: 'STALLED_VEHICLE', camera: { highway: 'NH-16', km: 42.4 }, vehicles: [{ cls: 'truck', lane: 'Fast lane' }] })
  it('says what and where', () => {
    expect(announcement(mk('a'))).toBe('Critical incident: Stalled truck in fast lane, NH-16 KM 42.4, fast lane.')
  })
  it('is silent for incidents already present at load, and speaks for new critical ones', () => {
    const { rerender } = render(<LiveAnnouncer list={[mk('old')]} conn="live" />)
    expect(screen.getByRole('alert').textContent).toBe('')
    rerender(<LiveAnnouncer list={[mk('old'), mk('new')]} conn="live" />)
    expect(screen.getByRole('alert').textContent).toMatch(/Critical incident: Stalled truck/)
  })
  it('does not shout for lower severities or resolved incidents', () => {
    const { rerender } = render(<LiveAnnouncer list={[mk('old')]} conn="live" />)
    rerender(<LiveAnnouncer list={[mk('old'), mk('w', 'P2'), mk('r', 'P0', 'resolved')]} conn="live" />)
    expect(screen.getByRole('alert').textContent).toBe('')
    expect(screen.getByRole('status').textContent).toMatch(/New incident/)
  })
  it('warns when the tracker goes offline with nothing on screen', () => {
    const { rerender } = render(<LiveAnnouncer list={[]} conn="live" />)
    rerender(<LiveAnnouncer list={[]} conn="offline" />)
    expect(screen.getByRole('alert').textContent).toMatch(/Cannot see the road/)
  })
})

// Real contrast check on the shipped stylesheet. WCAG AA for text is 4.5 to 1.
describe('colour contrast of the shipped theme tokens', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/styles/app.css'), 'utf8')
  const lum = (h) => {
    const c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
  }
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
  // The last definition in each theme block wins in the cascade.
  const last = (scope, name) => {
    let v = null
    for (const m of css.matchAll(new RegExp(`${scope.replace(/[[\]"().]/g, '\\$&')}\\s*\\{([^}]*)\\}`, 'g'))) {
      const d = m[1].match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})\\b`))
      if (d) v = d[1]
    }
    return v
  }
  const dark = ':root'; const light = ':root[data-theme="light"]'
  const cases = [
    ['dark faint text on panel', last(dark, '--faint'), last(dark, '--panel')],
    ['dark faint text on page', last(dark, '--faint'), last(dark, '--bg')],
    ['dark dim text on panel', last(dark, '--dim'), last(dark, '--panel')],
    ['home dark faint on surface', last(dark, '--premium-faint'), last(dark, '--premium-surface')],
    ['home light faint on white', last(light, '--premium-faint'), last(light, '--premium-surface')],
    ['home light faint on page', last(light, '--premium-faint'), last(light, '--premium-bg')],
    ['home light muted on white', last(light, '--premium-muted'), last(light, '--premium-surface')],
  ]
  for (const [name, fg, bg] of cases) {
    it(`${name} is at least 4.5:1`, () => {
      expect(fg, `${name}: foreground token found`).toBeTruthy(); expect(bg, `${name}: background token found`).toBeTruthy()
      expect(ratio(fg, bg)).toBeGreaterThanOrEqual(4.5)
    })
  }
})
