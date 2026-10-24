import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { connect } from '../api/client.js'
import { isActive } from '../lib/format.js'

export const initial = {
  incidents: {}, metrics: null, metricsAt: null, cameraHealth: null, cameraHealthAt: null,
  blackspots: [], camera: null, conn: 'connecting', selectedId: null,
}

export function reducer(s, a) {
  switch (a.type) {
    case 'conn': return { ...s, conn: a.conn }
    case 'select': return { ...s, selectedId: a.id }
    case 'event': {
      const e = a.event
      if (e.kind === 'snapshot') {
        const incidents = {}
        e.incidents.forEach((i) => { incidents[i.id] = i })
        const newest = Object.values(incidents).sort((x, y) => y.createdAt - x.createdAt)
        const pick = newest.find(isActive) || newest[0]
        // Keep the operator's selection only if that incident still exists after the refresh.
        const keep = s.selectedId && incidents[s.selectedId] ? s.selectedId : null
        return {
          ...s, incidents,
          blackspots: e.blackspots || s.blackspots,
          camera: e.camera || s.camera,
          selectedId: keep ?? pick?.id ?? null,
        }
      }
      if (e.kind === 'incident.upsert') {
        const current = s.selectedId ? s.incidents[s.selectedId] : null
        const isNew = !s.incidents[e.incident.id]
        // A new open incident takes focus only if nothing live is selected, so operators are not yanked away.
        const takeFocus = isNew && isActive(e.incident) && (!current || !isActive(current))
        return {
          ...s,
          incidents: { ...s.incidents, [e.incident.id]: e.incident },
          selectedId: takeFocus ? e.incident.id : s.selectedId ?? e.incident.id,
        }
      }
      if (e.kind === 'metrics') {
        const at = a.at ?? Date.now()
        return {
          ...s,
          metrics: e.metrics, metricsAt: at,
          cameraHealth: e.camera_health || s.cameraHealth,
          // A repeated health message is not proof the camera works. When the backend reports how
          // long ago the last video frame arrived, date the health from that frame, not from the message.
          cameraHealthAt: e.camera_health
            ? (Number.isFinite(e.camera_health.frame_age_s) ? at - e.camera_health.frame_age_s * 1000 : at)
            : s.cameraHealthAt,
        }
      }
      return s
    }
    default: return s
  }
}

// Counters on screen show whole seconds, so one tick a second is enough.
// (Ticking four times a second re-rendered the entire app four times a second.)
function useNow(ms = 1000) {
  const [n, setN] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setN(Date.now()), ms)
    return () => clearInterval(id)
  }, [ms])
  return n
}

export default function useControlRoom() {
  const [state, dispatch] = useReducer(reducer, initial)
  const link = useRef(null)
  const now = useNow()

  useEffect(() => {
    link.current = connect({
      onEvent: (event) => dispatch({ type: 'event', event }),
      onConn: (conn) => dispatch({ type: 'conn', conn }),
    })
    return () => link.current?.stop()
  }, [])

  const list = useMemo(
    () => Object.values(state.incidents).sort((a, b) => b.createdAt - a.createdAt),
    [state.incidents],
  )
  const selected = state.selectedId ? state.incidents[state.selectedId] || null : null

  const actions = {
    select: useCallback((id) => dispatch({ type: 'select', id }), []),
    cancelDispatch: useCallback((incId, dispId) => link.current?.cancelDispatch(incId, dispId), []),
    sendFeedback: useCallback((incId, verdict) => link.current?.sendFeedback(incId, verdict), []),
  }

  return { state, list, selected, now, actions }
}
