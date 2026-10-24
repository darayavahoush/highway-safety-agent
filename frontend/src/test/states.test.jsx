import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import IncidentQueue from '../components/IncidentQueue.jsx'
import ActivityLog from '../components/ActivityLog.jsx'
import ControlRoom from '../components/ControlRoom.jsx'
import { incidentWhy, vehicleSummary, isBlind } from '../lib/format.js'

afterEach(cleanup)

const truck = {
  id: 'a1', type: 'STALLED_VEHICLE', severity: 'P0', status: 'detected', createdAt: Date.now(),
  camera: { highway: 'NH-16', km: 42.4 },
  vehicles: [{ trackId: 12, cls: 'truck', speedKmh: 0, lane: 'Fast lane', plate: { text: 'AP39TB1234' } }],
  trace: [{ stage: 'observe', text: 'Truck #12 has been stationary in the fast lane for 3.8 s. Approaching traffic is moving at 62 to 78 km/h.' }],
  briefing: 'A truck has stopped. Risk is high.', dispatches: [],
}
const crash = { ...truck, id: 'a2', type: 'IMPACT', vehicles: [{ cls: 'car', speedKmh: 40 }, { cls: 'motorbike', speedKmh: 30 }], trace: [], briefing: 'A car and a motorbike appear to have collided in the slow lane. Injury is likely.' }

const queue = (props) => render(<IncidentQueue list={[]} selectedId={null} onSelect={() => {}} now={Date.now()} filter="active" setFilter={() => {}} {...props} />)

describe('incident card text', () => {
  it('why-line is the first sentence only, and does not split on decimals', () => {
    expect(incidentWhy(truck)).toBe('Truck #12 has been stationary in the fast lane for 3.8 s.')
  })
  it('why-line falls back to the briefing, then to empty', () => {
    expect(incidentWhy(crash)).toBe('A car and a motorbike appear to have collided in the slow lane.')
    expect(incidentWhy({ trace: [], briefing: '' })).toBe('')
  })
  it('vehicle summary shows type and speed for one vehicle, types for several', () => {
    expect(vehicleSummary(truck)).toBe('Truck · 0 km/h')
    expect(vehicleSummary(crash)).toBe('Car + Motorbike')
    expect(vehicleSummary({ vehicles: [] })).toBe('')
  })
  it('card shows the why-line, vehicle and plate', () => {
    queue({ list: [truck], conn: 'live' })
    expect(screen.getByText(/stationary in the fast lane for 3\.8 s\./)).toBeTruthy()
    expect(screen.getByText('Truck · 0 km/h')).toBeTruthy()
    expect(screen.getByText('AP39TB1234')).toBeTruthy()
  })
})

describe('empty, loading and offline states', () => {
  it('shows a loading placeholder while connecting, not "nothing here"', () => {
    queue({ conn: 'connecting' })
    expect(screen.getByRole('status').getAttribute('aria-busy')).toBe('true')
    expect(screen.queryByText(/nothing here yet/i)).toBeNull()
  })
  it('says it cannot reach the tracker when offline, instead of looking empty-and-fine', () => {
    queue({ conn: 'offline' })
    expect(screen.getByText(/can.t reach the tracker/i)).toBeTruthy()
    expect(screen.getByText(/does not mean the road is clear/i)).toBeTruthy()
  })
  it('shows a friendly empty message when connected and there are no incidents', () => {
    queue({ conn: 'live' })
    expect(screen.getByText(/nothing here yet/i)).toBeTruthy()
  })
  it('points to the All tab when only resolved incidents exist', () => {
    queue({ list: [{ ...truck, status: 'resolved' }], conn: 'live' })
    expect(screen.getByText(/no active incidents/i)).toBeTruthy()
    expect(screen.getByText(/switch to .all./i)).toBeTruthy()
  })
  it('activity log has loading, offline and empty states', () => {
    const { unmount } = render(<ActivityLog list={[]} onSelect={() => {}} conn="connecting" />)
    expect(screen.getByRole('status')).toBeTruthy(); unmount()
    const r2 = render(<ActivityLog list={[]} onSelect={() => {}} conn="offline" />)
    expect(screen.getByText(/can.t reach the tracker/i)).toBeTruthy(); r2.unmount()
    render(<ActivityLog list={[]} onSelect={() => {}} conn="demo" />)
    expect(screen.getByText(/no alerts sent yet/i)).toBeTruthy()
  })
})

describe('safety: never say "all clear" when the app cannot see', () => {
  it('isBlind only when empty AND connecting/offline', () => {
    expect(isBlind('offline', [])).toBe(true)
    expect(isBlind('connecting', [])).toBe(true)
    expect(isBlind('live', [])).toBe(false)
    expect(isBlind('offline', [truck])).toBe(false)
  })
  const hero = (conn) => render(
    <ControlRoom state={{ incidents: {}, metrics: null, cameraHealth: null, blackspots: [], camera: null, conn, selectedId: null }} list={[]} selected={null} now={Date.now()}
      actions={{ select() {} }} filter="active" setFilter={() => {}} camera={null} today={0} onCorridorInfo={() => {}} />,
  )
  it.each(['offline', 'connecting'])('control room hero does not say "All clear" when %s', (conn) => {
    hero(conn)
    expect(screen.queryByText(/all clear/i)).toBeNull()
  })
  it('control room hero still says "All clear" when connected and genuinely empty', () => {
    hero('live')
    expect(screen.getByText(/all clear/i)).toBeTruthy()
  })
})
