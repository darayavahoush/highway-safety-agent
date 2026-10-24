// Demo data source. Emits the same events the live backend should emit (see CONTRACT.md).

const CAMERA = {
  id: 'CAM-NH16-042', highway: 'NH-16', km: 42.4, lat: 16.5062, lng: 80.648,
  towards: 'Visakhapatnam', opposite: 'Vijayawada',
}
const BLACKSPOTS = [
  { km: 38, count: 2 }, { km: 39, count: 1 }, { km: 40, count: 4 }, { km: 41, count: 3 },
  { km: 42, count: 9 }, { km: 43, count: 7 }, { km: 44, count: 2 }, { km: 45, count: 1 },
  { km: 46, count: 3 }, { km: 47, count: 2 },
]
const CANCEL_WINDOW = 15000

const rnd = (a, b) => a + Math.random() * (b - a)
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)]
const rid = () => Math.floor(rnd(20, 480))
const LETTERS = 'ABCDEFGHJKLMNPRSTUVWXYZ'

function makePlate(low = false) {
  const state = pick(['AP', 'AP', 'AP', 'TS', 'TS', 'TN', 'KA'])
  const rto = String(Math.floor(rnd(1, 40))).padStart(2, '0')
  const series = pick(LETTERS) + (Math.random() < 0.7 ? pick(LETTERS) : '')
  const num = String(Math.floor(rnd(1, 9999))).padStart(4, '0')
  return {
    text: `${state} ${rto} ${series} ${num}`,
    confidence: +(low ? rnd(0.62, 0.78) : rnd(0.86, 0.98)).toFixed(2),
    votes: low ? 3 : Math.floor(rnd(4, 6)),
    frames: 5,
  }
}

const SCENARIOS = {
  STALLED_VEHICLE() {
    const v = { trackId: rid(), cls: 'truck', speedKmh: 0, lane: 'Fast lane', laneIndex: 1, x: 0.58, dir: 1, plate: makePlate() }
    return {
      severity: 'P0', confidence: 0.93, vehicles: [v],
      trace: [
        `Truck #${v.trackId} has been stationary in the fast lane for 3.8 s. Approaching traffic is moving at 62 to 78 km/h.`,
        'High-severity static obstacle. Following drivers do not have the sight distance to stop.',
        'Warn approaching drivers now and send a patrol with a crane. No sign of injury, so no ambulance.',
        'Variable message sign set 2 km upstream. NHAI patrol notified with plate and lane.',
      ],
      briefing: 'A truck has stopped in the fast lane at NH-16 KM 42.4 while traffic is still moving at speed. Rear-end collision risk is high. Upstream drivers are being warned and a patrol unit is on its way.',
      dispatches: [
        { target: 'VARIABLE_MESSAGE_SIGN_VMS', auto: true, message: 'Stalled vehicle ahead. Slow down.' },
        { target: 'HIGHWAY_PATROL_NHAI', auto: true, message: `Truck ${v.plate.text} stationary in fast lane, KM 42.4. Send patrol and crane.` },
      ],
    }
  },
  WRONG_WAY() {
    const v = { trackId: rid(), cls: 'car', speedKmh: 38, lane: 'Fast lane', laneIndex: 1, x: 0.78, dir: -1, plate: makePlate() }
    return {
      severity: 'P0', confidence: 0.96, vehicles: [v],
      trace: [
        `Car #${v.trackId} is moving against the lane direction at 38 km/h for 6 s.`,
        'Head-on collision risk with oncoming traffic. Time to impact is under 20 s at current closing speeds.',
        'Warn oncoming drivers immediately, alert police for interception and patrol for lane control.',
        'Variable message sign set to wrong-way warning. Police and NHAI patrol notified.',
      ],
      briefing: `A car (${v.plate.text}) is driving the wrong way in the fast lane at NH-16 KM 42.4. Oncoming drivers are being warned and police are being sent to intercept.`,
      dispatches: [
        { target: 'VARIABLE_MESSAGE_SIGN_VMS', auto: true, message: 'Wrong-way vehicle ahead. Keep left.' },
        { target: 'POLICE_CONTROL_ROOM', auto: false, message: `Wrong-way car ${v.plate.text}, NH-16 KM 42.4. Intercept.` },
        { target: 'HIGHWAY_PATROL_NHAI', auto: true, message: 'Wrong-way vehicle at KM 42.4. Support lane control.' },
      ],
    }
  },
  TAILGATING() {
    const a = { trackId: rid(), cls: 'truck', speedKmh: 71, lane: 'Slow lane', laneIndex: 0, x: 0.4, dir: 1, plate: makePlate() }
    const b = { trackId: rid(), cls: 'motorbike', speedKmh: 64, lane: 'Slow lane', laneIndex: 0, x: 0.47, dir: 1, plate: makePlate(true) }
    return {
      severity: 'P1', confidence: 0.88, vehicles: [a, b],
      trace: [
        `Truck #${a.trackId} is 1.4 m behind motorbike #${b.trackId} at 71 km/h. Time to collision is 0.3 s.`,
        'Dangerous but no impact yet. A heavy truck cannot stop in time if the bike slows.',
        'Record the violation with evidence. Send a patrol to the next exit and issue an owner notice. No emergency dispatch.',
        'Police control room notified. Owner notice queued for the truck.',
      ],
      briefing: 'A truck is following a motorbike far too closely in the slow lane at NH-16 KM 42.4. No collision yet. Evidence has been saved and the violation is being reported.',
      dispatches: [
        { target: 'POLICE_CONTROL_ROOM', auto: false, message: `Tailgating by truck ${a.plate.text}, KM 42.4. Clip attached.` },
        { target: 'VEHICLE_OWNER_NOTICE', auto: false, message: `Notice to registered owner of ${a.plate.text}: unsafe following distance.` },
      ],
    }
  },
  IMPACT() {
    const a = { trackId: rid(), cls: 'car', speedKmh: 0, lane: 'Slow lane', laneIndex: 0, x: 0.52, dir: 1, plate: makePlate() }
    const b = { trackId: rid(), cls: 'motorbike', speedKmh: 0, lane: 'Slow lane', laneIndex: 0, x: 0.545, dir: 1, plate: makePlate(true) }
    return {
      severity: 'P0', confidence: 0.78, vehicles: [a, b],
      trace: [
        `Car #${a.trackId} and motorbike #${b.trackId} overlapped, then both dropped from 58 km/h to 0 within 1.1 s.`,
        'Likely collision with a vulnerable road user. Injury probability is high. Confidence is moderate, so an operator should confirm.',
        'Dispatch an ambulance and patrol now. The ambulance goes out after a short operator cancel window.',
        'Ambulance queued. Patrol, police and variable message sign sent.',
      ],
      briefing: `A car and a motorbike appear to have collided in the slow lane at NH-16 KM 42.4. Injury is likely. An ambulance is queued with a short window for the operator to cancel. Patrol and police are on their way.`,
      dispatches: [
        { target: 'EMS_108_AMBULANCE', auto: false, message: 'Collision, car and motorbike, NH-16 KM 42.4 slow lane. Injury likely. Nearest trauma centre 6 km.' },
        { target: 'HIGHWAY_PATROL_NHAI', auto: true, message: 'Collision at KM 42.4. Secure the scene.' },
        { target: 'POLICE_CONTROL_ROOM', auto: true, message: `Collision involving ${a.plate.text}. Clip attached.` },
        { target: 'VARIABLE_MESSAGE_SIGN_VMS', auto: true, message: 'Accident ahead. Slow down.' },
      ],
    }
  },
}

const median = (xs) => {
  if (!xs.length) return null
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

export function startSimulator(emit) {
  const incidents = new Map()
  const timers = new Set()
  const dispTimers = new Map()
  const day = new Date().toISOString().slice(0, 10).replaceAll('-', '')
  let seq = 0
  let stopped = false

  const nextId = () => `INC-${day}-${String(++seq).padStart(4, '0')}`
  const later = (ms, fn) => {
    const t = setTimeout(() => { timers.delete(t); if (!stopped) fn() }, ms)
    timers.add(t)
    return t
  }
  const push = (inc) => emit({ kind: 'incident.upsert', incident: structuredClone(inc) })

  function scheduleAck(inc, disp) {
    later(rnd(5000, 14000), () => {
      if (disp.status !== 'sent') return
      disp.status = 'acknowledged'
      disp.ackAt = Date.now()
      const done = inc.dispatches.every((d) => ['acknowledged', 'cancelled'].includes(d.status))
      if (done && inc.status === 'dispatched') {
        inc.status = 'acknowledged'
        later(40000, () => { if (inc.status === 'acknowledged') { inc.status = 'resolved'; push(inc) } })
      }
      push(inc)
    })
  }

  function spawn(type) {
    const s = SCENARIOS[type]()
    const id = nextId()
    const inc = {
      id, type, severity: s.severity, status: 'detected', confidence: s.confidence,
      createdAt: Date.now(), camera: CAMERA,
      vehicles: s.vehicles.map((v) => ({ ...v, plate: null })),
      briefing: '', trace: [], dispatches: [], verdict: null,
    }
    const step = (stage, text) => inc.trace.push({ stage, text, at: Date.now() })
    incidents.set(id, inc)
    push(inc)

    later(900, () => {
      inc.status = 'analysing'
      inc.vehicles.forEach((v, i) => { v.plate = s.vehicles[i].plate })
      step('observed', s.trace[0]); push(inc)
    })
    later(2000, () => { step('assessed', s.trace[1]); push(inc) })
    later(3200, () => { step('decided', s.trace[2]); push(inc) })
    later(4300, () => {
      inc.briefing = s.briefing
      step('actions', s.trace[3])
      inc.status = 'dispatched'
      s.dispatches.forEach((d, i) => {
        const now = Date.now()
        const disp = {
          id: `${id}-D${i + 1}`, target: d.target, message: d.message,
          status: d.auto ? 'sent' : 'queued', queuedAt: now,
          sentAt: d.auto ? now : null, ackAt: null, cancelUntil: d.auto ? null : now + CANCEL_WINDOW,
        }
        inc.dispatches.push(disp)
        if (d.auto) scheduleAck(inc, disp)
        else {
          dispTimers.set(disp.id, later(CANCEL_WINDOW, () => {
            if (disp.status !== 'queued') return
            disp.status = 'sent'; disp.sentAt = Date.now()
            scheduleAck(inc, disp); push(inc)
          }))
        }
      })
      push(inc)
    })
  }

  function finished(type, ageMs, verdict) {
    const s = SCENARIOS[type]()
    const t0 = Date.now() - ageMs
    const id = nextId()
    const inc = {
      id, type, severity: s.severity, status: verdict === 'false_alarm' ? 'false_alarm' : 'resolved',
      confidence: s.confidence, createdAt: t0, camera: CAMERA, vehicles: s.vehicles,
      briefing: s.briefing, verdict,
      trace: ['observed', 'assessed', 'decided', 'actions'].map((stage, i) => ({ stage, text: s.trace[i], at: t0 + 900 + i * 1100 })),
      dispatches: s.dispatches.map((d, i) => ({
        id: `${id}-D${i + 1}`, target: d.target, message: d.message, status: 'acknowledged',
        queuedAt: t0 + 4300, sentAt: t0 + 4300 + (d.auto ? 0 : CANCEL_WINDOW), ackAt: t0 + 12000 + i * 3000, cancelUntil: null,
      })),
    }
    incidents.set(inc.id, inc)
    return inc
  }

  const history = [
    finished('TAILGATING', 3 * 3600e3 + 40 * 60e3, 'confirmed'),
    finished('STALLED_VEHICLE', 2 * 3600e3 + 10 * 60e3, 'confirmed'),
    finished('IMPACT', 25 * 60e3, 'false_alarm'),
  ]
  emit({ kind: 'snapshot', incidents: structuredClone(history), blackspots: BLACKSPOTS, camera: CAMERA })

  const order = ['STALLED_VEHICLE', 'TAILGATING', 'IMPACT', 'WRONG_WAY']
  let n = 0
  const loop = () => {
    spawn(order[n++ % order.length])
    later(rnd(26000, 38000), loop)
  }
  later(2500, loop)

  const metricsTimer = setInterval(() => {
    const dts = [...incidents.values()]
      .map((i) => i.dispatches.find((d) => d.sentAt))
      .map((d, idx) => (d ? (d.sentAt - [...incidents.values()][idx].createdAt) / 1000 : null))
      .filter((x) => x != null && x < 10)
    emit({
      kind: 'metrics',
      metrics: {
        fps: +rnd(23, 28).toFixed(1),
        cpuMsPerFrame: Math.round(rnd(31, 38)),
        ruleMs: +rnd(0.09, 0.14).toFixed(2),
        agentLatencyMs: Math.round(rnd(4100, 4700)),
        detectToDispatchS: median(dts) ?? 4.3,
      },
      camera_health: {
        camera_stability: 'STATIC_LOCKED',
        lighting_condition: 'OPTIMAL_DAYLIGHT',
        background_drift_px: +rnd(0.1, 0.5).toFixed(2),
        avg_luminance: Math.round(rnd(118, 138)),
        contrast_rms: Math.round(rnd(48, 56)),
        visibility_score: Math.round(rnd(93, 98)),
        motion_status: 'Static gantry mount',
      },
    })
  }, 1500)

  return {
    stop() { stopped = true; timers.forEach(clearTimeout); timers.clear(); clearInterval(metricsTimer) },
    async cancelDispatch(incId, dispId) {
      const inc = incidents.get(incId)
      const disp = inc?.dispatches.find((d) => d.id === dispId)
      if (!disp || disp.status !== 'queued') return
      clearTimeout(dispTimers.get(dispId))
      disp.status = 'cancelled'
      push(inc)
    },
    async sendFeedback(incId, verdict) {
      const inc = incidents.get(incId)
      if (!inc) return
      inc.verdict = verdict
      if (verdict === 'false_alarm') inc.status = 'false_alarm'
      push(inc)
    },
  }
}
