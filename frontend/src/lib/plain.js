// Plain-language helpers for the control room. No jargon, no codes.

export const SEVERITY_HELP = [
  ['P0', 'Critical', 'Act now'],
  ['P1', 'High', 'Check soon'],
  ['P2', 'Watch', 'Keep an eye on it'],
]

const WHY = {
  STALLED_VEHICLE: 'A vehicle has stopped in a live lane. Fast traffic behind it may not see it in time.',
  WRONG_WAY: 'A vehicle is travelling against the flow of traffic. A head-on crash is likely if it is not stopped quickly.',
  TAILGATING: 'Two vehicles are too close for their speed. One sudden brake could cause a pile-up.',
  IMPACT: 'The camera saw what looks like a collision. Medical help matters most in the first hour.',
}

export const whyItMatters = (type) => WHY[type] || 'The tracker saw something unusual on the road.'

export function nextStep(incident) {
  switch (incident.status) {
    case 'detected':
    case 'analysing':
      return 'The agent is checking the evidence and writing a briefing. You do not need to do anything yet.'
    case 'dispatched':
      return 'Alerts have been sent. Open “Dispatch history” to see who was told, then confirm it is real, or mark it a false alarm.'
    case 'acknowledged':
      return 'A responder has accepted this. Keep an eye on it and mark it real or a false alarm once you can tell.'
    default:
      return 'This incident is closed. Nothing more to do.'
  }
}

// Which photograph to use, based on the hour at the camera site (IST).
export function sceneFor(ms) {
  const h = Number(new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata', hour: '2-digit', hour12: false,
  }).format(new Date(ms))) % 24
  if (h >= 5 && h < 9) return 'daybreak'
  if (h >= 9 && h < 16) return 'day'
  if (h >= 16 && h < 19) return 'sunset'
  return 'night'
}

// Page headings, written for someone seeing the screen for the first time.
export const PAGE_COPY = {
  corridor: {
    kicker: 'Road map',
    title: 'Where is the road at risk?',
    lead: 'Pick a stretch of highway to see its weather, its past accident spots, and the nearest trauma hospital.',
  },
  incidents: {
    kicker: 'All incidents',
    title: 'Every incident, in one place',
    lead: 'Choose an incident on the left to see what happened, what the agent already did, and what to do next.',
  },
  activity: {
    kicker: 'Who was alerted',
    title: 'Who was told, and when',
    lead: 'Each row is one alert sent to a patrol, ambulance, police team or road sign. Click a row to open its incident.',
  },
  system: {
    kicker: 'Health check',
    title: 'Is everything working?',
    lead: 'Green means working. Amber means worth checking. Grey means the app has not been told yet.',
  },
}

// Plain wording for the camera's self-reported health.
export function cameraStatus(h) {
  if (!h) return { tone: 'idle', headline: 'Not reported yet', detail: 'The camera has not sent a health report.' }
  if (h.camera_stability === 'WIND_SWAY') return { tone: 'warn', headline: 'Swaying in the wind', detail: 'Detections may be a little less accurate until it settles.' }
  if (h.camera_stability === 'PANNING_OR_DRIFT') return { tone: 'warn', headline: 'Camera has moved', detail: 'The view has shifted. Lane positions may be off until it is re-aligned.' }
  if (h.visibility_score != null && h.visibility_score < 60) return { tone: 'warn', headline: 'Poor visibility', detail: 'Fog, rain or low light is reducing what the camera can see.' }
  return { tone: 'ok', headline: 'Steady and clear', detail: 'The camera is fixed in place and can see the road well.' }
}
