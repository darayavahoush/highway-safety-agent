import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { reducer, initial } from '../state/useControlRoom.js'
import { isStale } from '../lib/freshness.js'
import { hasCameraReport, cameraStatus } from '../lib/plain.js'
import { normalizeIncident } from '../api/normalize.js'
import PlateChip from '../components/PlateChip.jsx'

afterEach(cleanup)

describe('camera health is only trusted when video frames are actually arriving', () => {
  it('a heartbeat that says the last frame was 20 s ago is stale, even though the message is fresh', () => {
    const health = { camera_stability: 'STATIC_LOCKED', lighting_condition: 'OPTIMAL_DAYLIGHT', visibility_score: 96, frame_age_s: 20, frames_analysed: 500 }
    const s = reducer(initial, { type: 'event', at: 100_000, event: { kind: 'metrics', metrics: { fps: 25 }, camera_health: health } })
    expect(s.cameraHealthAt).toBe(80_000)
    expect(isStale(s.cameraHealthAt, 100_000)).toBe(true)
  })
  it('a recent frame is not stale', () => {
    const s = reducer(initial, { type: 'event', at: 100_000, event: { kind: 'metrics', camera_health: { camera_stability: 'STATIC_LOCKED', frame_age_s: 0.4 } } })
    expect(isStale(s.cameraHealthAt, 100_000)).toBe(false)
  })
  it('without frame_age_s (demo mode) health is dated from the message, as before', () => {
    const s = reducer(initial, { type: 'event', at: 5000, event: { kind: 'metrics', camera_health: { camera_stability: 'STATIC_LOCKED' } } })
    expect(s.cameraHealthAt).toBe(5000)
  })
  it('the backend’s "no frame yet" payload reads as NOT reported, never "Steady and clear"', () => {
    const none = { is_static: null, camera_stability: null, lighting_condition: null, visibility_score: null, frames_analysed: 0, frame_age_s: null, motion_status: 'No video frame analysed yet' }
    expect(hasCameraReport(none)).toBe(false)
    expect(cameraStatus(none).headline).toBe('Not reported yet')
  })
})

describe('an unreadable plate is never shown as a plate', () => {
  it('normalizing keeps readable=false', () => {
    const n = normalizeIncident({ id: 'a', type: 'STALLED_VEHICLE', vehicles: [{ track_id: 1, plate: { text: 'NO READ', readable: false, confidence: 0, votes: 0, frames: 6 } }] })
    expect(n.vehicles[0].plate.readable).toBe(false)
  })
  it('PlateChip says "No plate read" with no confidence bar and no plate text', () => {
    const { container } = render(<PlateChip plate={{ text: 'NO READ', readable: false, confidence: 0, votes: 0, frames: 6 }} />)
    expect(container.textContent).toMatch(/No plate read/)
    expect(container.textContent).not.toMatch(/NO READ|IND|%/)
    expect(container.querySelector('.conf')).toBeNull()
  })
  it('a normal read still shows the plate and its confidence', () => {
    const { container } = render(<PlateChip plate={{ text: 'AP 16 TX 4921', readable: true, confidence: 0.91, votes: 4, frames: 5 }} />)
    expect(container.textContent).toMatch(/AP 16 TX 4921/); expect(container.textContent).toMatch(/91%/)
  })
})
