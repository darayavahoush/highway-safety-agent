import { startSimulator } from './simulator.js'
import { normalizeEvent, normalizeIncident } from './normalize.js'

const MODE = String(import.meta.env.VITE_DATA_MODE || 'demo').toLowerCase()
const WS_PATH = import.meta.env.VITE_WS_PATH || '/ws/incidents'

export const isLive = MODE === 'live'

const post = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })

const SNAPSHOT_TIMEOUT_MS = 8000
const SNAPSHOT_RETRY_MS = 3000

// Live link to the backend. Exported so tests can drive it with a fake WebSocket and fetch.
//
// Reconnect rule: events that arrive while the snapshot is still downloading are held and
// replayed AFTER it, so a newer update is never overwritten by an older snapshot. If the
// snapshot is slow or fails, held events are released anyway so live updates are never blocked.
export function connectLive({ onEvent, onConn }) {
  let ws
  let closed = false
  let retry = 0
  let timer
  let generation = 0

  const open = () => {
    const gen = ++generation
    const stale = () => closed || gen !== generation
    let held = []
    let synced = false
    let snapTimer
    let abort

    const release = () => {
      synced = true
      const queued = held
      held = []
      queued.forEach(onEvent)
    }

    const loadSnapshot = () => {
      if (stale()) return
      abort = new AbortController()
      const killer = setTimeout(() => abort.abort(), SNAPSHOT_TIMEOUT_MS)
      fetch('/api/incidents', { signal: abort.signal })
        .then((r) => {
          if (!r.ok) throw new Error(`snapshot ${r.status}`)
          return r.json()
        })
        .then((d) => {
          if (stale()) return
          const list = Array.isArray(d) ? d : d.incidents || []
          onEvent({
            kind: 'snapshot',
            incidents: list.map(normalizeIncident),
            blackspots: d.blackspots,
            camera: d.camera,
          })
          release()
        })
        .catch(() => {
          if (stale()) return
          // Do not block live events on a failed snapshot; try again shortly.
          release()
          snapTimer = setTimeout(loadSnapshot, SNAPSHOT_RETRY_MS)
        })
        .finally(() => clearTimeout(killer))
    }

    onConn('connecting')
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${window.location.host}${WS_PATH}`)
    const mine = ws

    mine.onopen = () => {
      if (stale()) return
      retry = 0
      onConn('live')
      loadSnapshot()
    }
    mine.onmessage = (m) => {
      if (stale()) return
      try {
        const ev = normalizeEvent(JSON.parse(m.data))
        if (!ev) return
        if (synced || ev.kind === 'snapshot') onEvent(ev)
        else if (ev.kind === 'metrics') onEvent(ev) // metrics are idempotent, never hold them
        else held.push(ev)
      } catch { /* ignore malformed frames */ }
    }
    mine.onclose = () => {
      clearTimeout(snapTimer)
      abort?.abort()
      if (stale()) return
      onConn('offline')
      timer = setTimeout(open, Math.min(10000, 500 * 2 ** retry++))
    }
    mine.onerror = () => mine.close()
  }

  open()
  return () => {
    closed = true
    clearTimeout(timer)
    if (ws) ws.close()
  }
}

export function connect({ onEvent, onConn }) {
  if (isLive) {
    const stop = connectLive({ onEvent, onConn })
    return {
      stop,
      cancelDispatch: (incId, dispId) => post(`/api/incidents/${incId}/dispatches/${dispId}/cancel`),
      sendFeedback: (incId, verdict) => post(`/api/incidents/${incId}/feedback`, { verdict }),
    }
  }
  onConn('demo')
  const sim = startSimulator(onEvent)
  return { stop: sim.stop, cancelDispatch: sim.cancelDispatch, sendFeedback: sim.sendFeedback }
}

export async function fetchSystemStatus() {
  try {
    const r = await fetch('/api/status')
    if (r.ok) return await r.json()
  } catch {}
  return null
}
