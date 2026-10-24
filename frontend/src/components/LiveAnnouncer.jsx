import { useEffect, useRef, useState } from 'react'
import { incidentTitle, locationLabel, isActive, isBlind } from '../lib/format.js'

// Plain-language message for a screen reader. Exported so it can be tested.
export function announcement(incident) {
  const level = incident.severity === 'P0' ? 'Critical incident' : 'New incident'
  return `${level}: ${incidentTitle(incident)}, ${locationLabel(incident)}.`
}

// Speaks new incidents and connection loss. Nothing is spoken for incidents already on screen
// when the app first loads, so opening the page is not noisy.
// Critical incidents interrupt (assertive); everything else waits its turn (polite).
export default function LiveAnnouncer({ list, conn }) {
  const seen = useRef(null)
  const wasBlind = useRef(false)
  const [urgent, setUrgent] = useState('')
  const [polite, setPolite] = useState('')

  useEffect(() => {
    const ids = new Set(list.map((i) => i.id))
    if (seen.current === null) {
      if (list.length > 0 || (conn !== 'connecting')) seen.current = ids
      return
    }
    const fresh = list.filter((i) => !seen.current.has(i.id) && isActive(i))
    seen.current = ids
    if (fresh.length === 0) return
    const critical = fresh.filter((i) => i.severity === 'P0')
    if (critical.length) setUrgent(critical.map(announcement).join(' '))
    const rest = fresh.filter((i) => i.severity !== 'P0')
    if (rest.length) setPolite(rest.map(announcement).join(' '))
  }, [list, conn])

  useEffect(() => {
    const blind = isBlind(conn, list)
    if (blind && !wasBlind.current && conn === 'offline') setUrgent('Cannot see the road right now. The tracker is unreachable. An empty list does not mean the road is clear.')
    if (!blind && wasBlind.current) setPolite('Tracker connection restored.')
    wasBlind.current = blind
  }, [conn, list])

  return (
    <>
      <div className="sr-only" role="alert" aria-live="assertive" aria-atomic="true">{urgent}</div>
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{polite}</div>
    </>
  )
}
