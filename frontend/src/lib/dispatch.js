// Honest wording for dispatch states.
//
// Rule: a status we do not recognise, or one that means "failed" or "no answer",
// is NEVER shown as sent, acknowledged or cancelled. A timeout means the outcome is
// unknown, not that help is on the way.

export const KNOWN = ['queued', 'sent', 'acknowledged', 'cancelled']

export const isProblem = (d) => !KNOWN.includes(d?.status)

export function problemText(status) {
  switch (status) {
    case 'failed':
    case 'rejected':
    case 'error':
      return 'Failed. This alert was not delivered. Contact the responder directly.'
    case 'unconfirmed':
    case 'timeout':
    case 'timed_out':
      return 'No confirmation received. The outcome is unknown. Treat it as not delivered until someone confirms.'
    default:
      return 'Unrecognised status. The outcome is unknown. Check with the responder directly.'
  }
}

export const problemLabel = (status) => (
  ['failed', 'rejected', 'error'].includes(status) ? 'Failed' : 'Not confirmed'
)

// What the operator should do next, based on what the dispatches actually did.
export function dispatchNextStep(dispatches = []) {
  if (dispatches.some(isProblem)) {
    return 'At least one alert failed or is not confirmed. Do not assume help is coming. Contact the responder directly, then confirm the incident is real or mark it a false alarm.'
  }
  if (dispatches.some((d) => d.status === 'queued')) {
    return 'Alerts are queued and go out when the cancel window ends. Cancel only if this is a false alarm.'
  }
  if (dispatches.some((d) => d.status === 'sent')) {
    return 'Alerts were sent but nobody has acknowledged yet. Open “Dispatch history”, then confirm it is real or mark it a false alarm.'
  }
  return null
}
