import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { connectLive } from '../api/client.js'
import { reducer, initial } from '../state/useControlRoom.js'
import { isStale } from '../lib/freshness.js'

class FakeWS {
  static all = []
  constructor() { FakeWS.all.push(this) }
  close() { this.onclose?.() }
}
const inc = (id, status = 'detected', extra = {}) => ({ id, type: 'STALLED_VEHICLE', status, created_at: 1_700_000_000_000, ...extra })

let fetchResolvers
beforeEach(() => {
  vi.useFakeTimers()
  FakeWS.all = []
  fetchResolvers = []
  vi.stubGlobal('WebSocket', FakeWS)
  vi.stubGlobal('fetch', vi.fn((url, opts) => new Promise((resolve, reject) => {
    fetchResolvers.push({ resolve, reject })
    opts?.signal?.addEventListener('abort', () => reject(new Error('aborted')))
  })))
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve() }
const snapshotResponse = (list) => ({ ok: true, json: async () => ({ incidents: list }) })

function start() {
  const events = []; const conns = []
  const stop = connectLive({ onEvent: (e) => events.push(e), onConn: (c) => conns.push(c) })
  return { events, conns, stop, ws: () => FakeWS.all.at(-1) }
}

describe('reconnect', () => {
  it('replays updates that arrived during the snapshot download AFTER the snapshot', async () => {
    const { events, ws } = start()
    ws().onopen()
    ws().onmessage({ data: JSON.stringify({ incident: inc('a', 'dispatched') }) })
    expect(events.filter((e) => e.kind === 'incident.upsert')).toHaveLength(0) // held
    fetchResolvers[0].resolve(snapshotResponse([inc('a', 'detected')]))
    await flush()
    expect(events.map((e) => e.kind)).toEqual(['snapshot', 'incident.upsert'])
    const state = events.reduce((s, event) => reducer(s, { type: 'event', event }), initial)
    expect(state.incidents.a.status).toBe('dispatched') // newer update survived
  })

  it('does not block live events when the snapshot fails, and retries it', async () => {
    const { events, ws } = start()
    ws().onopen()
    ws().onmessage({ data: JSON.stringify({ incident: inc('b') }) })
    fetchResolvers[0].resolve({ ok: false, status: 500, json: async () => ({}) })
    await flush()
    expect(events.some((e) => e.kind === 'incident.upsert')).toBe(true)
    ws().onmessage({ data: JSON.stringify({ incident: inc('c') }) })
    expect(events.filter((e) => e.kind === 'incident.upsert')).toHaveLength(2) // flowing again
    await vi.advanceTimersByTimeAsync(3100)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('gives up on a stalled snapshot after the timeout and releases held events', async () => {
    const { events, ws } = start()
    ws().onopen()
    ws().onmessage({ data: JSON.stringify({ incident: inc('d') }) })
    await vi.advanceTimersByTimeAsync(8100)
    expect(events.some((e) => e.kind === 'incident.upsert')).toBe(true)
  })

  it('ignores a snapshot that finishes after the socket dropped', async () => {
    const { events, conns, ws } = start()
    const first = ws()
    first.onopen()
    first.close()
    expect(conns.at(-1)).toBe('offline')
    fetchResolvers[0].resolve(snapshotResponse([inc('x')]))
    await flush()
    expect(events.filter((e) => e.kind === 'snapshot')).toHaveLength(0)
  })

  it('a late close from an old socket does not break the new one', async () => {
    const { conns, ws } = start()
    const old = ws()
    old.onopen(); old.close()
    await vi.advanceTimersByTimeAsync(600)
    const fresh = ws()
    expect(fresh).not.toBe(old)
    fresh.onopen()
    old.onclose() // stray late event
    expect(conns.at(-1)).toBe('live')
  })

  it('stop() prevents any further reconnects', async () => {
    const { stop, ws } = start()
    ws().onopen()
    stop()
    await vi.advanceTimersByTimeAsync(20000)
    expect(FakeWS.all).toHaveLength(1)
  })
})

describe('reducer', () => {
  const snap = (...ids) => ({ type: 'event', event: { kind: 'snapshot', incidents: ids.map((id) => ({ id, status: 'detected', createdAt: Number(id.slice(1)) })) } })

  it('keeps the operator selection if the incident still exists after a refresh', () => {
    let s = reducer(initial, snap('i1', 'i2'))
    s = reducer(s, { type: 'select', id: 'i1' })
    s = reducer(s, snap('i1', 'i2', 'i3'))
    expect(s.selectedId).toBe('i1')
  })

  it('moves selection off an incident that vanished, instead of pointing at nothing', () => {
    let s = reducer(initial, snap('i1', 'i2'))
    s = reducer(s, { type: 'select', id: 'i1' })
    s = reducer(s, snap('i2'))
    expect(s.selectedId).toBe('i2')
  })

  it('records when metrics and camera health last arrived', () => {
    const s = reducer(initial, { type: 'event', at: 5000, event: { kind: 'metrics', metrics: { fps: 25 }, camera_health: { camera_stability: 'STATIC_LOCKED' } } })
    expect(s.metricsAt).toBe(5000)
    expect(s.cameraHealthAt).toBe(5000)
    const s2 = reducer(s, { type: 'event', at: 9000, event: { kind: 'metrics', metrics: { fps: 24 } } })
    expect(s2.metricsAt).toBe(9000)
    expect(s2.cameraHealthAt).toBe(5000) // camera health did not refresh
  })
})

describe('freshness', () => {
  it('is stale only after the limit, and never when nothing has ever arrived', () => {
    expect(isStale(1000, 5000)).toBe(false)
    expect(isStale(1000, 9500)).toBe(true)
    expect(isStale(null, 99999)).toBe(false)
  })
})
