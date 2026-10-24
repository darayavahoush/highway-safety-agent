import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react'
import App from '../App.jsx'

afterEach(() => { cleanup(); vi.useRealTimers() })
const settle = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(1500) }) }
const selectedTab = () => document.querySelector('.stage [role="tab"][aria-selected="true"]')?.textContent || ''
async function openCorridor() {
  vi.useFakeTimers()
  render(<App />); await settle()
  fireEvent.click(screen.getAllByRole('button', { name: /enter|open|control room|launch|start/i })[0]); await settle()
  fireEvent.click([...document.querySelectorAll('.ops-nav-link')].find((b) => b.textContent.includes('Corridor'))); await settle()
}

describe('Corridor tab keys', () => {
  it('a bare number switches tab, but Ctrl/Cmd+number, typing and an open dialog do not', async () => {
    await openCorridor()
    const start = selectedTab()
    fireEvent.keyDown(window, { key: '3' }); await settle()
    expect(selectedTab()).toMatch(/Lanes/)
    fireEvent.keyDown(window, { key: '4', ctrlKey: true }); await settle()
    expect(selectedTab()).toMatch(/Lanes/)
    fireEvent.keyDown(window, { key: '4', metaKey: true }); await settle()
    expect(selectedTab()).toMatch(/Lanes/)
    const input = document.createElement('input'); document.body.appendChild(input)
    fireEvent.keyDown(input, { key: '4' }); await settle()
    expect(selectedTab()).toMatch(/Lanes/)
    input.remove()
    fireEvent.keyDown(window, { key: '?' }); await settle()
    expect(screen.getByRole('dialog')).toBeTruthy()
    fireEvent.keyDown(window, { key: '1' }); await settle()
    expect(selectedTab()).toMatch(/Lanes/)
    expect(start).not.toMatch(/Lanes/)
  })
})
