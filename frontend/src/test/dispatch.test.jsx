import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import DispatchTimeline from '../components/DispatchTimeline.jsx'
import ActivityLog from '../components/ActivityLog.jsx'
import { nextStep } from '../lib/plain.js'
import { normalizeIncident } from '../api/normalize.js'

afterEach(cleanup)
const disp = (status, extra = {}) => ({ id: `d-${status}`, target: 'EMS_108_AMBULANCE', status, message: '', queuedAt: 1000, sentAt: 2000, ...extra })
const inc = (dispatches, status = 'dispatched') => ({ id: 'i1', type: 'IMPACT', status, createdAt: 1000, vehicles: [], dispatches })

describe('a failed or unconfirmed dispatch is never shown as sent or cancelled', () => {
  for (const status of ['failed', 'rejected', 'unconfirmed', 'timeout', 'weird_new_status']) {
    it(`timeline: "${status}"`, () => {
      render(<DispatchTimeline incident={inc([disp(status)])} now={5000} onCancel={() => {}} />)
      const text = document.querySelector('.disp--problem')?.textContent || ''
      expect(text).toMatch(/not delivered|unknown/i)
      expect(text).not.toMatch(/Cancelled by operator|Sent, waiting|Acknowledged/)
    })
  }
  it('activity log counts and labels problems, never "sent"', () => {
    render(<ActivityLog list={[inc([disp('failed'), disp('timeout', { id: 'd2' })])]} onSelect={() => {}} conn="live" />)
    expect(screen.getByLabelText('Alert summary').textContent).toMatch(/2 failed or not confirmed/)
    expect(document.querySelectorAll('.chip--problem').length).toBeGreaterThanOrEqual(3)
    expect(document.body.textContent).not.toMatch(/\bSent\b/)
  })
  it('a missing status from the backend is unknown, not sent', () => {
    const n = normalizeIncident({ id: 'x', type: 'IMPACT', status: 'dispatched', dispatches: [{ id: 'd1', target: 'EMS_108_AMBULANCE' }] })
    expect(n.dispatches[0].status).toBe('unknown')
  })
})

describe('next step matches what the dispatches actually did', () => {
  it('failed beats everything', () => {
    expect(nextStep(inc([disp('acknowledged'), disp('failed', { id: 'b' })]))).toMatch(/failed or is not confirmed.*Contact the responder/s)
  })
  it('queued does not claim anything was sent', () => {
    const t = nextStep(inc([disp('queued')]))
    expect(t).toMatch(/queued/); expect(t).not.toMatch(/have been sent|were sent/)
  })
  it('sent but unacknowledged says nobody has acknowledged', () => {
    expect(nextStep(inc([disp('sent')]))).toMatch(/nobody has acknowledged/)
  })
})
