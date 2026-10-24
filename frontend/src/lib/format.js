import {
  AlertTriangle, ArrowLeftRight, CarFront, Siren,
  Signpost, ShieldAlert, Radio, Ambulance, Mail, Send,
} from 'lucide-react'

export const TYPE_META = {
  STALLED_VEHICLE: { label: 'Vehicle on shoulder / Stalled', icon: AlertTriangle },
  WRONG_WAY: { label: 'Wrong-way driving', icon: ArrowLeftRight },
  TAILGATING: { label: 'Dangerous tailgating', icon: CarFront },
  FEEDER_INTRUSION: { label: 'Feeder road intrusion', icon: Signpost },
  IMPACT: { label: 'Possible crash', icon: Siren },
}

export const TARGET_META = {
  VARIABLE_MESSAGE_SIGN_VMS: { label: 'Variable message sign', icon: Signpost, endpoint: '/mock/vms_gantry' },
  HIGHWAY_PATROL_NHAI: { label: 'NHAI highway patrol', icon: ShieldAlert, endpoint: '/mock/nhai' },
  POLICE_CONTROL_ROOM: { label: 'Police control room', icon: Radio, endpoint: '/mock/police' },
  EMS_108_AMBULANCE: { label: '108 ambulance', icon: Ambulance, endpoint: '/mock/ems_108' },
  VEHICLE_OWNER_NOTICE: { label: 'Vehicle owner notice', icon: Mail, endpoint: '/mock/owner_notice' },
}

export function targetMeta(target = '') {
  return (
    TARGET_META[target] || {
      label: target.replaceAll('_', ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()),
      icon: Send,
      endpoint: '',
    }
  )
}

export const SEVERITY = {
  P0: { label: 'P0 Critical', color: 'var(--red)', badge: 'CRITICAL HAZARD' },
  P1: { label: 'P1 High', color: 'var(--amber)', badge: 'HIGH HAZARD' },
  P2: { label: 'P2 Monitored', color: 'var(--blue)', badge: 'MONITORED' },
}

export const STATUS_LABEL = {
  detected: 'Detected',
  analysing: 'Agent analysing',
  dispatched: 'Dispatched',
  monitoring: 'Monitored',
  acknowledged: 'Acknowledged',
  resolved: 'Resolved',
  false_alarm: 'False alarm',
}

export const isActive = (i) => !['resolved', 'false_alarm'].includes(i.status)

const cap = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)

export function incidentTitle(i) {
  const v = i.vehicles || []
  const a = v[0]
  const lane = a?.lane ? ` in ${a.lane.toLowerCase()}` : ''
  switch (i.type) {
    case 'STALLED_VEHICLE': {
      if (a?.lane && a.lane.toLowerCase().includes('shoulder')) {
        return a ? `${cap(a.cls)} on shoulder` : 'Vehicle on shoulder'
      }
      return a ? `Stalled ${a.cls}${lane}` : 'Stalled vehicle'
    }
    case 'WRONG_WAY': return a ? `Wrong-way ${a.cls}` : 'Wrong-way driving'
    case 'TAILGATING': return a && v[1] ? `${cap(a.cls)} tailgating ${v[1].cls}` : 'Dangerous tailgating'
    case 'FEEDER_INTRUSION': return a ? `${cap(a.cls)} feeder road intrusion` : 'Feeder road intrusion'
    case 'IMPACT': return 'Possible crash'
    default: return TYPE_META[i.type]?.label || 'Incident'
  }
}

export function locationLabel(i) {
  const c = i.camera || {}
  const lane = i.vehicles?.[0]?.lane
  return `${c.highway || 'Highway'} KM ${c.km ?? '?'}${lane ? `, ${lane.toLowerCase()}` : ''}`
}

export function fmtDuration(ms) {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(sec).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

export function fmtAge(ms) {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s} s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  return `${Math.floor(m / 60)} h ${m % 60} min ago`
}

export const fmtOffset = (ms) => `+${(Math.max(0, ms) / 1000).toFixed(1)} s`

const clock = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
})
export const fmtClock = (ms) => clock.format(new Date(ms))

export const VEHICLE_LABEL = { truck: 'Truck', bus: 'Bus', car: 'Car', van: 'Van', motorbike: 'Motorbike' }

// True when we have no data AND no working connection. An empty list then means
// "we cannot see", not "all clear", so screens must not show reassurance.
export const isBlind = (conn, list) => list.length === 0 && (conn === 'connecting' || conn === 'offline')

const firstSentence = (text = '') => {
  const t = String(text).trim().replace(/\s+/g, ' ')
  const m = t.match(/^.*?[.!?](?=\s|$)/)
  return (m ? m[0] : t).trim()
}

// One line saying why the system flagged this, from the tracker's own first note.
export function incidentWhy(i) {
  return firstSentence(i.trace?.[0]?.text) || firstSentence(i.briefing) || ''
}

// "Truck · 0 km/h" for one vehicle, "Truck + Motorbike" for several.
export function vehicleSummary(i) {
  const vs = i.vehicles || []
  if (vs.length === 0) return ''
  const name = (v) => VEHICLE_LABEL[v.cls] || (v.cls ? v.cls.charAt(0).toUpperCase() + v.cls.slice(1) : 'Vehicle')
  if (vs.length === 1) {
    const sp = vs[0].speedKmh
    return Number.isFinite(sp) ? `${name(vs[0])} · ${Math.round(sp)} km/h` : name(vs[0])
  }
  return [...new Set(vs.map(name))].join(' + ')
}
