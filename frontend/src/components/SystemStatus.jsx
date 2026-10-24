import { Wifi, Camera, Gauge, Timer, Database, Eye } from 'lucide-react'
import StatsStrip from './StatsStrip.jsx'
import { isActive } from '../lib/format.js'
import { cameraStatus } from '../lib/plain.js'

function connection(conn) {
  switch (conn) {
    case 'live': return { tone: 'ok', headline: 'Connected', detail: 'The app is receiving live data from the backend.' }
    case 'demo': return { tone: 'warn', headline: 'Running on demo data', detail: 'No live backend is attached, so incidents on screen are simulated.' }
    case 'offline': return { tone: 'bad', headline: 'Cannot reach the backend', detail: 'The app is retrying on its own. New incidents will not appear until it reconnects.' }
    default: return { tone: 'idle', headline: 'Connecting…', detail: 'Waiting for the first message from the backend.' }
  }
}

function tracker(m) {
  if (m?.fps == null) return { tone: 'idle', headline: 'Not reported yet', detail: 'The video tracker has not sent its speed.' }
  if (m.fps < 5) return { tone: 'warn', headline: `${m.fps} frames a second`, detail: 'That is slow. Fast incidents could be spotted late.' }
  return { tone: 'ok', headline: `${m.fps} frames a second`, detail: 'Fast enough to follow vehicles smoothly.' }
}

function reaction(m) {
  const s = m?.detectToDispatchS
  if (s == null) return { tone: 'idle', headline: 'Not measured yet', detail: 'This appears after the first incident is handled.' }
  return { tone: s > 10 ? 'warn' : 'ok', headline: `${s.toFixed(1)} seconds`, detail: 'Time from the camera spotting a problem to the first alert going out.' }
}

export default function SystemStatus({ state, list, camera, today }) {
  const open = list.filter(isActive).length
  const cards = [
    [Wifi, 'Connection', connection(state.conn)],
    [Camera, 'Camera', cameraStatus(state.cameraHealth)],
    [Gauge, 'Video tracker', tracker(state.metrics)],
    [Timer, 'Speed of response', reaction(state.metrics)],
    [Database, 'Incident records', {
      tone: 'ok',
      headline: `${list.length} on file`,
      detail: `${open} still open. ${today} seen today.`,
    }],
  ]
  return (
    <>
      <div className="cr-health">
        {cards.map(([Icon, label, c]) => (
          <article key={label} className="cr-health-card" data-tone={c.tone}>
            <span className="cr-health-label"><Icon size={15} aria-hidden="true" />{label}</span>
            <b><i aria-hidden="true" />{c.headline}</b>
            <p>{c.detail}</p>
          </article>
        ))}
      </div>
      <details className="cr-tech">
        <summary><Eye size={14} aria-hidden="true" />Technical performance <span>for engineers</span></summary>
        <StatsStrip metrics={state.metrics} open={open} today={today} blackspots={state.blackspots} camera={camera} />
      </details>
    </>
  )
}
