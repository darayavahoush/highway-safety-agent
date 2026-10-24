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
