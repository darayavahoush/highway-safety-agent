import {
  AlertTriangle, ArrowLeftRight, CarFront, Siren,
  Signpost, ShieldAlert, Radio, Ambulance, Mail, Send,
} from 'lucide-react'

export const TYPE_META = {
  STALLED_VEHICLE: { label: 'Stalled vehicle', icon: AlertTriangle },
  WRONG_WAY: { label: 'Wrong-way driving', icon: ArrowLeftRight },
  TAILGATING: { label: 'Dangerous tailgating', icon: CarFront },
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
  P0: { label: 'Critical', color: 'var(--red)' },
  P1: { label: 'High', color: 'var(--amber)' },
  P2: { label: 'Watch', color: 'var(--blue)' },
}

export const STATUS_LABEL = {
  detected: 'Detected',
  analysing: 'Agent analysing',
  dispatched: 'Dispatched',
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
    case 'STALLED_VEHICLE': return a ? `Stalled ${a.cls}${lane}` : 'Stalled vehicle'
    case 'WRONG_WAY': return a ? `Wrong-way ${a.cls}` : 'Wrong-way driving'
    case 'TAILGATING': return a && v[1] ? `${cap(a.cls)} tailgating ${v[1].cls}` : 'Dangerous tailgating'
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
