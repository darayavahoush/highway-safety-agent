import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react'
import App from '../App.jsx'

afterEach(() => { cleanup(); vi.useRealTimers() })
const settle = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(1500) }) }
async function enter() {
  vi.useFakeTimers()
  render(<App />); await settle()
  fireEvent.click(screen.getAllByRole('button', { name: /enter|open|control room|launch|start/i })[0]); await settle()
}
const current = () => document.querySelector('.ops-nav-link[aria-current="page"]')?.textContent || ''

describe('top bar and banner', () => {
  it('the camera badge opens System status, where its details live', async () => {
    await enter()
    fireEvent.click(document.querySelector('.cam-health-badge-btn'))
    await settle()
    expect(current()).toMatch(/System status/)
  })
  it('the help button says Help and opens the help window', async () => {
    await enter()
    const btn = screen.getByRole('button', { name: /help and keyboard shortcuts/i })
    expect(btn.textContent).toMatch(/Help/)
    fireEvent.click(btn); await settle()
    expect(screen.getByRole('dialog')).toBeTruthy()
  })
  it('the severity legend is tucked away until asked for', async () => {
    await enter()
    const wrap = document.querySelector('.cr-legend-wrap')
    expect(wrap).toBeTruthy()
    expect(wrap.hasAttribute('open')).toBe(false)
    expect(wrap.querySelector('summary').textContent).toMatch(/severity labels/i)
    expect(wrap.querySelectorAll('li')).toHaveLength(3) // content is still there for screen readers and on click
  })
})
