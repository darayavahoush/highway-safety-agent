// Smoke test: open every page of the real app (demo mode) and fail if anything
// throws or logs a React/console error. This catches crashes, not visual
// layout. For layout, check in a real browser.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react'
import App from '../App.jsx'

const PAGES = ['Overview', 'Corridor', 'Incidents', 'Activity', 'System status']

let errorSpy
beforeEach(() => {
  vi.useFakeTimers()
  errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  errorSpy.mockRestore()
})

// The page buttons in the main navigation (other buttons share some of these words).
const navButton = (label) =>
  [...document.querySelectorAll('.ops-nav-link')].find((b) => b.textContent.toLowerCase().includes(label.toLowerCase()))

const settle = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(1500) }) }

describe('every page opens without errors', () => {
  it('home page renders', async () => {
    render(<App />)
    await settle()
    expect(document.body.textContent.length).toBeGreaterThan(50)
    expect(errorSpy).not.toHaveBeenCalled()
  })

  for (const label of PAGES) {
    it(`"${label}" page renders`, async () => {
      render(<App />)
      await settle()
      fireEvent.click(screen.getAllByRole('button', { name: /enter|open|control room|launch|start/i })[0])
      await settle()
      expect(navButton(label), `nav button "${label}" exists`).toBeTruthy()
      fireEvent.click(navButton(label))
      await settle()
      expect(navButton(label).getAttribute('aria-current')).toBe('page')
      expect(document.body.textContent).not.toMatch(/something went wrong|undefined|NaN|\[object Object\]/i)
      expect(errorSpy).not.toHaveBeenCalled()
    })
  }

  it('a theme is applied on load without errors', async () => {
    render(<App />)
    await settle()
    expect(document.documentElement.dataset.theme).toBeTruthy()
    expect(errorSpy).not.toHaveBeenCalled()
  })
})
