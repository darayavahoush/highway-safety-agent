// Turns whatever the backend sends into the shape the UI expects.
// Adjust the field aliases here if the backend schema differs. Do not touch components.

const toMs = (v) => {
  if (v == null) return null
  if (typeof v === 'number') return v < 1e12 ? v * 1000 : v
  const t = Date.parse(v)
  return Number.isNaN(t) ? null : t
}

function normPlate(p) {
  if (!p) return null
  if (typeof p === 'string') return { text: p, confidence: 0.8, votes: 1, frames: 1, readable: true }
  return {
    text: p.text ?? p.plate ?? '',
    confidence: p.confidence ?? 0.8,
    votes: p.votes ?? 1,
    frames: p.frames ?? p.total_frames ?? 1,
    readable: p.readable !== false && !!(p.text ?? p.plate),
  }
}

export function normalizeIncident(r) {
  const createdAt = toMs(r.createdAt ?? r.created_at ?? r.timestamp) ?? Date.now()
  return {
    id: r.id ?? r.incident_id,
    type: String(r.type ?? r.incident_type ?? '').toUpperCase(),
    severity: r.severity ?? r.priority ?? 'P1',
    status: String(r.status ?? 'detected').toLowerCase(),
    confidence: r.confidence ?? null,
    createdAt,
    camera: r.camera ?? {
      id: r.camera_id, highway: r.highway ?? 'NH-16', km: r.km_marker ?? r.km,
    },
    vehicles: (r.vehicles ?? []).map((v) => ({
      trackId: v.trackId ?? v.track_id,
      cls: String(v.cls ?? v.vehicle_class ?? 'car').toLowerCase(),
      speedKmh: v.speedKmh ?? v.speed_kmh ?? 0,
      lane: v.lane ?? null,
      laneIndex: v.laneIndex ?? v.lane_index ?? 1,
      x: v.x ?? 0.5,
      dir: v.dir ?? 1,
      plate: normPlate(v.plate),
    })),
    briefing: r.briefing ?? '',
    trace: (r.trace ?? r.reasoning ?? []).map((s) => ({
      stage: String(s.stage).toLowerCase(),
      text: s.text,
      at: toMs(s.at ?? s.timestamp) ?? createdAt,
    })),
    dispatches: (r.dispatches ?? []).map((d) => ({
      id: d.id ?? d.dispatch_id,
      target: String(d.target ?? d.stakeholder ?? '').toUpperCase(),
      status: String(d.status ?? 'unknown').toLowerCase(),
      message: d.message ?? d.summary ?? '',
      queuedAt: toMs(d.queuedAt ?? d.queued_at) ?? toMs(d.sentAt ?? d.sent_at) ?? createdAt,
      sentAt: toMs(d.sentAt ?? d.sent_at),
      ackAt: toMs(d.ackAt ?? d.ack_at),
      cancelUntil: toMs(d.cancelUntil ?? d.cancel_until),
    })),
    verdict: r.verdict ?? null,
  }
}

export function normalizeEvent(e) {
  if (!e) return null
  if (e.incidents) {
    return { kind: 'snapshot', incidents: e.incidents.map(normalizeIncident), blackspots: e.blackspots, camera: e.camera, system_status: e.system_status }
  }
  if (e.incident) return { kind: 'incident.upsert', incident: normalizeIncident(e.incident) }
  if (e.metrics) return { kind: 'metrics', metrics: e.metrics, camera_health: e.camera_health, system_status: e.system_status }
  if (e.kind === 'status' || e.system_status) return { kind: 'status', system_status: e.system_status || e.status }
  return null
}
