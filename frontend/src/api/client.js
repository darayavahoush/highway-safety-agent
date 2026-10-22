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

function connectLive({ onEvent, onConn }) {
  let ws
  let closed = false
  let retry = 0
  let timer

  const open = () => {
    onConn('connecting')
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${window.location.host}${WS_PATH}`)

    ws.onopen = () => {
      retry = 0
      onConn('live')
      fetch('/api/incidents')
        .then((r) => r.json())
        .then((d) => {
          const list = Array.isArray(d) ? d : d.incidents || []
          onEvent({
            kind: 'snapshot',
            incidents: list.map(normalizeIncident),
            blackspots: d.blackspots,
            camera: d.camera,
          })
        })
        .catch(() => {})
    }
    ws.onmessage = (m) => {
      try {
        const ev = normalizeEvent(JSON.parse(m.data))
        if (ev) onEvent(ev)
      } catch { /* ignore malformed frames */ }
    }
    ws.onclose = () => {
      if (closed) return
      onConn('offline')
      timer = setTimeout(open, Math.min(10000, 500 * 2 ** retry++))
    }
    ws.onerror = () => ws.close()
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
