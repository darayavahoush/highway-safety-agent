import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react'
import { resolveShortcut, CHORD_MS } from '../lib/shortcuts.js'
import { withFreshness } from '../components/SystemStatus.jsx'
import CameraHealthBadge from '../components/CameraHealthBadge.jsx'
import App from '../App.jsx'

afterEach(cleanup)
const key = (k, extra = {}) => ({ key: k, target: document.body, ...extra })
const ctx = { page: 'control', aboutOpen: false, now: 10_000 }

describe('resolveShortcut', () => {
  it('Cmd/Ctrl+A is select-all, not "open About"', () => {
    expect(resolveShortcut(key('a', { metaKey: true }), ctx).action).toBeNull()
    expect(resolveShortcut(key('a', { ctrlKey: true }), ctx).action).toBeNull()
    expect(resolveShortcut(key('a'), ctx).action).toEqual({ type: 'about', open: true })
  })
  it('ignores keys typed into inputs', () => {
    const input = document.createElement('input')
    expect(resolveShortcut({ key: '?', target: input }, ctx).action).toBeNull()
  })
  it('G then a number jumps to that page, and only within the time window', () => {
    const g = resolveShortcut(key('g'), ctx)
    expect(g.chord).toBe(10_000)
    const jump = resolveShortcut(key('3'), { ...ctx, chordAt: g.chord, now: 10_500 })
    expect(jump.action).toEqual({ type: 'page', page: 'incidents' })
    expect(jump.consume).toBe(true)
    expect(resolveShortcut(key('3'), { ...ctx, chordAt: 10_000, now: 10_000 + CHORD_MS + 1 }).action).toBeNull()
  })
  it('a bare number does nothing (it belongs to the Corridor tabs)', () => {
    expect(resolveShortcut(key('2'), ctx)).toEqual({ action: null, chord: null })
  })
  it('does nothing page-related on the home page', () => {
    expect(resolveShortcut(key('g'), { ...ctx, page: 'home' }).chord).toBeNull()
    expect(resolveShortcut(key('h'), { ...ctx, page: 'home' }).action).toBeNull()
  })
  it('Esc closes About first, then leaves the control room', () => {
    expect(resolveShortcut(key('Escape'), { ...ctx, aboutOpen: true }).action).toEqual({ type: 'about', open: false })
    expect(resolveShortcut(key('Escape'), ctx).action).toEqual({ type: 'page', page: 'home' })
    expect(resolveShortcut(key('Escape'), { ...ctx, page: 'system' }).action).toBeNull()
  })
  it('does not navigate while About is open', () => {
    expect(resolveShortcut(key('h'), { ...ctx, aboutOpen: true }).action).toBeNull()
  })
})

describe('stale data', () => {
  const ok = { tone: 'ok', headline: 'Steady and clear', detail: '' }
  it('card turns amber and names the last known state once reports stop', () => {
    const c = withFreshness(ok, 1000, 21_000, 'The camera')
    expect(c.tone).toBe('warn')
    expect(c.headline).toBe('No update for 20 s')
    expect(c.detail).toMatch(/steady and clear/)
  })
  it('fresh and never-reported cards are untouched', () => {
    expect(withFreshness(ok, 1000, 3000, 'x')).toBe(ok)
    expect(withFreshness(ok, null, 99_000, 'x')).toBe(ok)
  })
  it('top-bar badge shows the age instead of a confident STATIC/DAYLIGHT', () => {
    render(<CameraHealthBadge health={{ camera_stability: 'STATIC_LOCKED', lighting_condition: 'OPTIMAL_DAYLIGHT' }} staleSeconds={14} />)
    expect(screen.getByText(/LAST REPORT 14 S AGO/)).toBeTruthy()
    expect(screen.queryByText('STATIC')).toBeNull()
  })
})

describe('in the app', () => {
  const settle = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(1500) }) }
  const current = () => document.querySelector('.ops-nav-link[aria-current="page"]')?.textContent || ''

  it('G then 5 opens System status; a lone G or lone number does not move you', async () => {
    vi.useFakeTimers()
    try {
      render(<App />)
      await settle()
      fireEvent.click(screen.getAllByRole('button', { name: /enter|open|control room|launch|start/i })[0])
      await settle()
      expect(current()).toMatch(/Overview/)
      fireEvent.keyDown(window, { key: '5' })
      expect(current()).toMatch(/Overview/)
      fireEvent.keyDown(window, { key: 'g' })
      fireEvent.keyDown(window, { key: '5' })
      await settle()
      expect(current()).toMatch(/System status/)
      fireEvent.keyDown(window, { key: 'g' })
      fireEvent.keyDown(window, { key: '3' })
      await settle()
      expect(current()).toMatch(/Incidents/)
    } finally { vi.useRealTimers() }
  })
})
